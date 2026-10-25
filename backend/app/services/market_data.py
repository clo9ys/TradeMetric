from collections.abc import Sequence
from datetime import date, timedelta, timezone

from app.db.models import InstrumentSnapshot
from app.db.uow import UnitOfWork
from app.domain.enums import CouponType, MarketDataSource, PriceType, QuoteKind
from app.domain.errors import IncompleteMarketDataError, StaleMarketDataError
from app.domain.isin import validate_isin
from app.domain.market_data import NormalizedBondData
from app.providers.base import BondDataProvider

MOSCOW = timezone(timedelta(hours=3))


def snapshot_to_data(snapshot: InstrumentSnapshot) -> NormalizedBondData:
    try:
        source = MarketDataSource(snapshot.source)
        quote_kind = QuoteKind(snapshot.quote_kind)
        price_type = PriceType(snapshot.price_type)
        coupon_type = CouponType(snapshot.coupon_type)
    except (TypeError, ValueError) as error:
        raise IncompleteMarketDataError(
            "Сохранённый снимок содержит неизвестный тип данных"
        ) from error
    return NormalizedBondData.from_provider(
        isin=snapshot.isin,
        source=source,
        currency=snapshot.currency,
        nominal_per_bond=snapshot.nominal_per_bond,
        quote_kind=quote_kind,
        quote_value=snapshot.quote_value,
        price_type=price_type,
        quote_source=snapshot.quote_source,
        quote_as_of_date=snapshot.quote_as_of_date,
        coupon_type=coupon_type,
        fetched_at=snapshot.fetched_at,
        accrued_per_bond=snapshot.accrued_per_bond,
        accrued_as_of_date=snapshot.accrued_as_of_date,
        coupon_frequency=snapshot.coupon_frequency,
        modified_duration=snapshot.modified_duration,
        convexity=snapshot.convexity,
        risk_as_of_date=snapshot.risk_as_of_date,
        provider_instrument_id=snapshot.provider_instrument_id,
        issue_name=snapshot.issue_name,
        issuer_name=snapshot.issuer_name,
        quote_as_of_at=snapshot.quote_as_of_at,
        risk_as_of_at=snapshot.risk_as_of_at,
    )


def _to_snapshot(data: NormalizedBondData) -> InstrumentSnapshot:
    return InstrumentSnapshot(
        isin=data.isin,
        source=data.source.value,
        currency=data.currency,
        nominal_per_bond=data.nominal_per_bond,
        quote_kind=data.quote_kind.value,
        quote_value=data.quote_value,
        price_type=data.price_type.value,
        quote_source=data.quote_source,
        quote_as_of_date=data.quote_as_of_date,
        coupon_type=data.coupon_type.value,
        fetched_at=data.fetched_at,
        accrued_per_bond=data.accrued_per_bond,
        accrued_as_of_date=data.accrued_as_of_date,
        coupon_frequency=data.coupon_frequency,
        modified_duration=data.modified_duration,
        convexity=data.convexity,
        risk_as_of_date=data.risk_as_of_date,
        provider_instrument_id=data.provider_instrument_id,
        issue_name=data.issue_name,
        issuer_name=data.issuer_name,
        quote_as_of_at=data.quote_as_of_at,
        risk_as_of_at=data.risk_as_of_at,
    )


class MarketDataService:
    def __init__(self, uow: UnitOfWork, cbonds: BondDataProvider) -> None:
        self._uow = uow
        self._cbonds = cbonds

    async def resolve_snapshots(
        self,
        isins: Sequence[str],
        *,
        calculation_date: date,
        last_trading_date: date,
    ) -> dict[str, InstrumentSnapshot]:
        unique_isins = list(dict.fromkeys(validate_isin(isin) for isin in isins))
        if not unique_isins:
            return {}

        async with self._uow as uow:
            cached = await uow.snapshots.get_fetched_on_date(unique_isins, calculation_date)

        resolved: dict[str, InstrumentSnapshot] = {}
        for snapshot in cached:
            if snapshot.isin in resolved:
                continue
            try:
                data = snapshot_to_data(snapshot)
                data.validate_freshness(
                    calculation_date=calculation_date,
                    last_trading_date=last_trading_date,
                )
            except (IncompleteMarketDataError, StaleMarketDataError):
                continue
            resolved[snapshot.isin] = snapshot

        new_snapshots: list[InstrumentSnapshot] = []
        for isin in unique_isins:
            if isin in resolved:
                continue
            data = await self._cbonds.get_bond(isin)
            if data.isin != isin or data.source is not MarketDataSource.CBONDS:
                raise IncompleteMarketDataError(
                    "Cbonds вернул данные другого инструмента или источника"
                )
            data.validate_freshness(
                calculation_date=calculation_date,
                last_trading_date=last_trading_date,
            )
            if data.fetched_at.astimezone(MOSCOW).date() != calculation_date:
                raise StaleMarketDataError("Данные Cbonds загружены не в день расчёта по Москве")
            snapshot = _to_snapshot(data)
            new_snapshots.append(snapshot)
            resolved[isin] = snapshot

        if new_snapshots:
            async with self._uow as uow:
                await uow.snapshots.add_many(new_snapshots)
                await uow.commit()

        return {isin: resolved[isin] for isin in unique_isins}
