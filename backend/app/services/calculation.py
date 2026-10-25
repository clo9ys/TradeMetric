from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import CouponType, PriceType, QuoteKind
from app.domain.errors import FXRateUnavailableError, IncompleteMarketDataError
from app.domain.market_data import NormalizedBondData
from app.domain.position import validate_quantity

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
    dv01 = fair_value * (
        -duration * RATE_SHIFT + Decimal("0.5") * convexity * RATE_SHIFT**2
    )
    return TradeMetrics(
        dirty_price_per_bond=price,
        current_fair_value_rub=fair_value,
        duration_used=duration,
        convexity_used=convexity,
        dv01_rub=dv01,
    )


def calculate_total_dv01(trades: Sequence[TradeMetrics]) -> Decimal:
    return sum((trade.dv01_rub for trade in trades), Decimal(0))
