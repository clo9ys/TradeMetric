import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domain.enums import CouponType, MarketDataSource, PriceType, QuoteKind
from app.domain.errors import FXRateUnavailableError, InvalidCalculationError, InvalidQuantityError
from app.domain.market_data import NormalizedBondData
from app.providers.fx import FXRate
from app.services.calculation import CalculationService, TradeRequest
from app.services.market_data import PreparedMarketData, _to_snapshot

CALCULATION_DATE = date(2026, 10, 25)
TRADING_DATE = date(2026, 10, 23)
ISIN = "XS0157815647"
NOW = datetime(2026, 10, 25, 12, tzinfo=UTC)


def bond_data() -> NormalizedBondData:
    return NormalizedBondData(
        isin=ISIN,
        source=MarketDataSource.CBONDS,
        currency="USD",
        nominal_per_bond=Decimal("1000"),
        quote_kind=QuoteKind.AMOUNT,
        quote_value=Decimal("1043.125"),
        price_type=PriceType.DIRTY,
        quote_source="synthetic test",
        quote_as_of_date=TRADING_DATE,
        coupon_type=CouponType.FIXED,
        fetched_at=NOW,
        modified_duration=Decimal("2"),
        convexity=Decimal("10"),
        risk_as_of_date=TRADING_DATE,
    )


class FakeMarketData:
    def __init__(self, *, cached: bool = False):
        self.snapshot = _to_snapshot(bond_data())
        if cached:
            self.snapshot.id = uuid.uuid4()
        self.calls = []
        self.cached = cached

    async def prepare_snapshots(self, isins, *, calculation_date, last_trading_date):
        self.calls.append((isins, calculation_date, last_trading_date))
        new = () if self.cached else (self.snapshot,)
        return PreparedMarketData({ISIN: self.snapshot}, new)


class FakeFXProvider:
    def __init__(self, *, fail: bool = False):
        self.calls = []
        self.fail = fail

    async def get_rate(self, currency, calculation_date):
        self.calls.append((currency, calculation_date))
        if self.fail:
            raise FXRateUnavailableError("Курс недоступен")
        return FXRate(Decimal("80.5"), TRADING_DATE, "CBR")


class FakeSnapshotRepository:
    def __init__(self):
        self.added = []

    async def add_many(self, snapshots):
        self.added.extend(snapshots)
        for snapshot in snapshots:
            snapshot.id = uuid.uuid4()


class FakeCalculationRepository:
    def __init__(self, *, fail: bool = False):
        self.added = []
        self.fail = fail

    async def add(self, calculation, trades):
        if self.fail:
            raise RuntimeError("Ошибка сохранения")
        calculation.id = uuid.uuid4()
        for trade in trades:
            trade.id = uuid.uuid4()
        self.added.append((calculation, trades))


class FakeUnitOfWork:
    def __init__(self, *, fail: bool = False):
        self.snapshots = FakeSnapshotRepository()
        self.calculations = FakeCalculationRepository(fail=fail)
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def commit(self):
        self.commits += 1


def requests() -> list[TradeRequest]:
    return [
        TradeRequest(uuid.uuid4(), ISIN, 3),
        TradeRequest(uuid.uuid4(), ISIN, -1),
    ]


@pytest.mark.asyncio
async def test_repeated_isin_and_currency_are_loaded_once_but_trades_remain_separate():
    uow = FakeUnitOfWork()
    market = FakeMarketData()
    fx = FakeFXProvider()
    user_id = uuid.uuid4()
    service = CalculationService(uow, market, fx, clock=lambda: NOW)

    result = await service.calculate(user_id, requests(), last_trading_date=TRADING_DATE)

    assert market.calls == [([ISIN], CALCULATION_DATE, TRADING_DATE)]
    assert fx.calls == [("USD", CALCULATION_DATE)]
    assert len(uow.snapshots.added) == 1
    assert uow.commits == 1
    assert len(uow.calculations.added) == 1
    calculation, saved_trades = uow.calculations.added[0]
    assert calculation.id == result.id
    assert [trade.quantity for trade in saved_trades] == [3, -1]
    assert saved_trades[0].snapshot_id == saved_trades[1].snapshot_id
    assert [trade.fx_rate_rub for trade in saved_trades] == [Decimal("80.5")] * 2
    assert [trade.fx_effective_date for trade in saved_trades] == [TRADING_DATE] * 2
    assert result.total_dv01_rub == sum((trade.dv01 for trade in saved_trades), Decimal(0))
    assert [trade.line_number for trade in result.trades] == [1, 2]


@pytest.mark.asyncio
async def test_cached_snapshot_is_reused_without_new_snapshot_write():
    uow = FakeUnitOfWork()
    market = FakeMarketData(cached=True)
    service = CalculationService(uow, market, FakeFXProvider(), clock=lambda: NOW)

    result = await service.calculate(uuid.uuid4(), requests(), last_trading_date=TRADING_DATE)

    assert uow.snapshots.added == []
    assert result.trades[0].snapshot_id == market.snapshot.id
    assert result.trades[1].snapshot_id == market.snapshot.id
    assert uow.commits == 1


@pytest.mark.asyncio
async def test_invalid_second_line_stops_before_data_access_or_transaction():
    uow = FakeUnitOfWork()
    market = FakeMarketData()
    fx = FakeFXProvider()
    service = CalculationService(uow, market, fx, clock=lambda: NOW)
    trades = requests()
    trades[1] = TradeRequest(trades[1].client_trade_id, ISIN, 0)

    with pytest.raises(InvalidQuantityError):
        await service.calculate(uuid.uuid4(), trades, last_trading_date=TRADING_DATE)

    assert market.calls == []
    assert fx.calls == []
    assert uow.commits == 0


@pytest.mark.asyncio
async def test_fx_failure_stops_before_transaction():
    uow = FakeUnitOfWork()
    fx = FakeFXProvider(fail=True)
    service = CalculationService(uow, FakeMarketData(), fx, clock=lambda: NOW)

    with pytest.raises(FXRateUnavailableError):
        await service.calculate(uuid.uuid4(), requests(), last_trading_date=TRADING_DATE)

    assert uow.snapshots.added == []
    assert uow.calculations.added == []
    assert uow.commits == 0


@pytest.mark.asyncio
async def test_save_failure_never_commits():
    uow = FakeUnitOfWork(fail=True)
    service = CalculationService(uow, FakeMarketData(), FakeFXProvider(), clock=lambda: NOW)

    with pytest.raises(RuntimeError, match="Ошибка сохранения"):
        await service.calculate(uuid.uuid4(), requests(), last_trading_date=TRADING_DATE)

    assert uow.commits == 0


@pytest.mark.asyncio
async def test_empty_or_duplicate_client_ids_are_rejected():
    uow = FakeUnitOfWork()
    service = CalculationService(uow, FakeMarketData(), FakeFXProvider(), clock=lambda: NOW)
    user_id = uuid.uuid4()
    with pytest.raises(InvalidCalculationError, match="хотя бы одну"):
        await service.calculate(user_id, [], last_trading_date=TRADING_DATE)
    repeated_id = uuid.uuid4()
    repeated = [TradeRequest(repeated_id, ISIN, 1), TradeRequest(repeated_id, ISIN, 2)]
    with pytest.raises(InvalidCalculationError, match="повторяться"):
        await service.calculate(user_id, repeated, last_trading_date=TRADING_DATE)
    assert uow.commits == 0
