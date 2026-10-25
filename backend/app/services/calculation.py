import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from app.db.models import Calculation, CalculationTrade
from app.db.uow import UnitOfWork
from app.domain.enums import CouponType, PriceType, QuoteKind
from app.domain.errors import (
    FXRateUnavailableError,
    IncompleteMarketDataError,
    InvalidCalculationError,
)
from app.domain.isin import validate_isin
from app.domain.market_data import NormalizedBondData
from app.domain.position import validate_quantity
from app.providers.fx import FXRate, FXRateProvider
from app.services.market_data import MOSCOW, MarketDataService, snapshot_to_data

RATE_SHIFT = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class TradeMetrics:
    dirty_price_per_bond: Decimal
    current_fair_value_rub: Decimal
    duration_used: Decimal
    convexity_used: Decimal
    dv01_rub: Decimal


def calculate_trade_metrics(
    bond: NormalizedBondData, quantity: int, fx_rate: Decimal
) -> TradeMetrics:
    validate_quantity(quantity)
    if not isinstance(fx_rate, Decimal) or not fx_rate.is_finite() or fx_rate <= 0:
        raise FXRateUnavailableError("Курс к рублю должен быть положительным Decimal")
    if bond.currency == "RUB" and fx_rate != 1:
        raise FXRateUnavailableError("Для рублёвой облигации курс должен быть равен 1")

    price = bond.quote_value
    if bond.quote_kind is QuoteKind.PERCENT:
        price = price * bond.nominal_per_bond / Decimal("100")
    if bond.price_type is PriceType.CLEAN:
        if bond.accrued_per_bond is None:
            raise IncompleteMarketDataError("Для чистой цены необходим НКД")
        price += bond.accrued_per_bond

    if bond.coupon_type is CouponType.FLOATING:
        if bond.coupon_frequency is None:
            raise IncompleteMarketDataError("Для плавающего купона нужна частота выплат")
        duration = Decimal(1) / Decimal(bond.coupon_frequency)
        convexity = Decimal(0)
    else:
        if bond.modified_duration is None or bond.convexity is None:
            raise IncompleteMarketDataError("Для фиксированного купона необходимы риск-параметры")
        duration = bond.modified_duration
        convexity = bond.convexity

    fair_value = Decimal(quantity) * price * fx_rate
    dv01 = fair_value * (-duration * RATE_SHIFT + Decimal("0.5") * convexity * RATE_SHIFT**2)
    return TradeMetrics(
        dirty_price_per_bond=price,
        current_fair_value_rub=fair_value,
        duration_used=duration,
        convexity_used=convexity,
        dv01_rub=dv01,
    )


def calculate_total_dv01(trades: Sequence[TradeMetrics]) -> Decimal:
    return sum((trade.dv01_rub for trade in trades), Decimal(0))


@dataclass(frozen=True, slots=True)
class TradeRequest:
    client_trade_id: uuid.UUID
    isin: str
    quantity: int


@dataclass(frozen=True, slots=True)
class CalculatedTrade:
    id: uuid.UUID
    client_trade_id: uuid.UUID
    line_number: int
    isin: str
    quantity: int
    snapshot_id: uuid.UUID
    currency: str
    fx_rate: FXRate
    metrics: TradeMetrics


@dataclass(frozen=True, slots=True)
class CalculationResult:
    id: uuid.UUID
    user_id: uuid.UUID
    calculated_at: datetime
    total_dv01_rub: Decimal
    trades: tuple[CalculatedTrade, ...]


class CalculationService:
    def __init__(
        self,
        uow: UnitOfWork,
        market_data: MarketDataService,
        fx_provider: FXRateProvider | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow = uow
        self._market_data = market_data
        self._fx_provider = fx_provider
        self._clock = clock or (lambda: datetime.now(UTC))

    async def calculate(
        self,
        user_id: uuid.UUID,
        trades: Sequence[TradeRequest],
        *,
        last_trading_date: date,
    ) -> CalculationResult:
        
        if not isinstance(user_id, uuid.UUID):
            raise InvalidCalculationError("Не указан пользователь расчёта")
        if not trades:
            raise InvalidCalculationError("Добавьте хотя бы одну строку расчёта")

        normalized: list[TradeRequest] = []
        client_ids: set[uuid.UUID] = set()

        for trade in trades:
            if not isinstance(trade.client_trade_id, uuid.UUID):
                raise InvalidCalculationError("У каждой строки должен быть client_trade_id")
            if trade.client_trade_id in client_ids:
                raise InvalidCalculationError("client_trade_id не должен повторяться")
            
            client_ids.add(trade.client_trade_id)
            normalized.append(
                TradeRequest(
                    client_trade_id=trade.client_trade_id,
                    isin=validate_isin(trade.isin),
                    quantity=validate_quantity(trade.quantity),
                )
            )

        requested_at = self._clock()
        if requested_at.tzinfo is None or requested_at.utcoffset() is None:
            raise ValueError("Время расчёта должно содержать часовой пояс")
        calculation_date = requested_at.astimezone(MOSCOW).date()
        if type(last_trading_date) is not date or last_trading_date > calculation_date:
            raise InvalidCalculationError("Некорректная дата последнего торгового дня")

        prepared = await self._market_data.prepare_snapshots(
            list(dict.fromkeys(trade.isin for trade in normalized)),
            calculation_date=calculation_date,
            last_trading_date=last_trading_date,
        )
        bonds = {isin: snapshot_to_data(snapshot) for isin, snapshot in prepared.snapshots.items()}
        fx_rates: dict[str, FXRate] = {}
        for currency in dict.fromkeys(bond.currency for bond in bonds.values()):
            if currency == "RUB":
                fx_rates[currency] = FXRate(Decimal(1), calculation_date, "RUB")
                continue
            if self._fx_provider is None:
                raise FXRateUnavailableError(f"Не настроен источник курса {currency}")
            rate = await self._fx_provider.get_rate(currency, calculation_date)
            if (
                not isinstance(rate.rub_per_unit, Decimal)
                or not rate.rub_per_unit.is_finite()
                or rate.rub_per_unit <= 0
                or type(rate.effective_date) is not date
                or rate.effective_date > calculation_date
                or not isinstance(rate.source, str)
                or not rate.source.strip()
            ):
                raise FXRateUnavailableError(f"Нет действующего курса {currency} на дату расчёта")
            fx_rates[currency] = rate

        metrics = [
            calculate_trade_metrics(
                bonds[trade.isin],
                trade.quantity,
                fx_rates[bonds[trade.isin].currency].rub_per_unit,
            )
            for trade in normalized
        ]
        calculated_at = self._clock()
        calculation = Calculation(
            user_id=user_id,
            requested_at=requested_at,
            calculated_at=calculated_at,
            methodology_version="dv01-python-v1",
            data_policy_version="last-trading-day-v1",
            warnings=[],
        )

        async with self._uow as uow:
            if prepared.new_snapshots:
                await uow.snapshots.add_many(prepared.new_snapshots)
            saved_trades = [
                CalculationTrade(
                    snapshot_id=prepared.snapshots[trade.isin].id,
                    client_trade_id=trade.client_trade_id,
                    line_number=line_number,
                    quantity=trade.quantity,
                    current_fair_value=result.current_fair_value_rub,
                    duration_used=result.duration_used,
                    convexity_used=result.convexity_used,
                    dv01=result.dv01_rub,
                    fx_rate_rub=fx_rates[bonds[trade.isin].currency].rub_per_unit,
                    fx_effective_date=fx_rates[bonds[trade.isin].currency].effective_date,
                    fx_source=fx_rates[bonds[trade.isin].currency].source,
                )

                # для нумерации
                for line_number, (trade, result) in enumerate(
                    zip(normalized, metrics, strict=True), 1
                )
            ]
            await uow.calculations.add(calculation, saved_trades)
            await uow.commit()

        return CalculationResult(
            id=calculation.id,
            user_id=user_id,
            calculated_at=calculated_at,
            total_dv01_rub=calculate_total_dv01(metrics),
            trades=tuple(
                CalculatedTrade(
                    id=saved_trade.id,
                    client_trade_id=trade.client_trade_id,
                    line_number=line_number,
                    isin=trade.isin,
                    quantity=trade.quantity,
                    snapshot_id=saved_trade.snapshot_id,
                    currency=bonds[trade.isin].currency,
                    fx_rate=fx_rates[bonds[trade.isin].currency],
                    metrics=result,
                )
                for line_number, (trade, saved_trade, result) in enumerate(
                    zip(normalized, saved_trades, metrics, strict=True), 1
                )
            ),
        )
