import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.dialects import postgresql

from app.db.repositories.snapshot import SnapshotRepository
from app.domain.enums import CouponType, MarketDataSource, PriceType, QuoteKind
from app.domain.errors import (
    IncompleteMarketDataError,
    ProviderUnavailableError,
    StaleMarketDataError,
)
from app.domain.market_data import NormalizedBondData
from app.services.market_data import MarketDataService, _to_snapshot

CALCULATION_DATE = date(2026, 10, 25)
LAST_TRADING_DATE = date(2026, 10, 23)
MOSCOW = timezone(timedelta(hours=3))
FIRST_ISIN = "RU000A10D4Y2"
SECOND_ISIN = "XS0157815647"


def bond_data(
    isin: str = FIRST_ISIN,
    *,
    quote_date: date = LAST_TRADING_DATE,
    fetched_at: datetime = datetime(2026, 10, 24, 22, tzinfo=UTC),
    source: MarketDataSource = MarketDataSource.CBONDS,
) -> NormalizedBondData:
    return NormalizedBondData.from_provider(
        isin=isin,
        source=source,
        currency="RUB",
        nominal_per_bond=Decimal("1000"),
        quote_kind=QuoteKind.AMOUNT,
        quote_value=Decimal("986.12"),
        price_type=PriceType.DIRTY,
        quote_source="Test exchange",
        quote_as_of_date=quote_date,
        coupon_type=CouponType.FIXED,
        fetched_at=fetched_at,
        modified_duration=Decimal("4.5"),
        convexity=Decimal("25"),
        risk_as_of_date=quote_date,
    )


class FakeSnapshotRepository:
    def __init__(self, records=None):
        self.records = list(records or [])
        self.added = []
        self.lookups = []

    async def get_fetched_on_date(self, isins, calculation_date):
        self.lookups.append((list(isins), calculation_date))
        return sorted(
            (
                record
                for record in self.records
                if record.isin in isins
                and record.fetched_at.astimezone(MOSCOW).date() == calculation_date
            ),
            key=lambda record: record.fetched_at,
            reverse=True,
        )

    async def add_many(self, records):
        for record in records:
            record.id = uuid.uuid4()
        self.records.extend(records)
        self.added.extend(records)


class FakeUnitOfWork:
    def __init__(self, snapshots):
        self.snapshots = snapshots
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def commit(self):
        self.commits += 1


class FakeProvider:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def get_bond(self, isin):
        self.calls.append(isin)
        result = self.responses[isin]
        if isinstance(result, Exception):
            raise result
        return result


def cached(data):
    snapshot = _to_snapshot(data)
    snapshot.id = uuid.uuid4()
    return snapshot


@pytest.mark.asyncio
async def test_fresh_cached_snapshot_skips_cbonds_and_write():
    snapshot = cached(bond_data())
    repository = FakeSnapshotRepository([snapshot])
    uow = FakeUnitOfWork(repository)
    provider = FakeProvider({})

    result = await MarketDataService(uow, provider).resolve_snapshots(
        [FIRST_ISIN], calculation_date=CALCULATION_DATE, last_trading_date=LAST_TRADING_DATE
    )

    assert result == {FIRST_ISIN: snapshot}
    assert provider.calls == []
    assert repository.added == []
    assert uow.commits == 0


@pytest.mark.asyncio
async def test_valid_cached_snapshot_from_other_source_is_reused():
    snapshot = cached(bond_data(source=MarketDataSource.RUDATA))
    provider = FakeProvider({})

    result = await MarketDataService(
        FakeUnitOfWork(FakeSnapshotRepository([snapshot])), provider
    ).resolve_snapshots(
        [FIRST_ISIN], calculation_date=CALCULATION_DATE, last_trading_date=LAST_TRADING_DATE
    )

    assert result[FIRST_ISIN] is snapshot
    assert provider.calls == []


@pytest.mark.asyncio
async def test_previous_moscow_day_snapshot_does_not_satisfy_cache():
    previous_day = cached(bond_data(fetched_at=datetime(2026, 10, 24, 20, tzinfo=UTC)))
    repository = FakeSnapshotRepository([previous_day])
    uow = FakeUnitOfWork(repository)
    provider = FakeProvider({FIRST_ISIN: bond_data()})

    result = await MarketDataService(uow, provider).resolve_snapshots(
        [FIRST_ISIN], calculation_date=CALCULATION_DATE, last_trading_date=LAST_TRADING_DATE
    )

    assert result[FIRST_ISIN] is not previous_day
    assert provider.calls == [FIRST_ISIN]
    assert len(repository.added) == 1
    assert uow.commits == 1


@pytest.mark.asyncio
async def test_stale_cached_quote_is_replaced_from_cbonds():
    stale = cached(bond_data(quote_date=date(2026, 10, 22)))
    repository = FakeSnapshotRepository([stale])
    provider = FakeProvider({FIRST_ISIN: bond_data()})

    result = await MarketDataService(FakeUnitOfWork(repository), provider).resolve_snapshots(
        [FIRST_ISIN], calculation_date=CALCULATION_DATE, last_trading_date=LAST_TRADING_DATE
    )

    assert result[FIRST_ISIN] is repository.added[0]
    assert provider.calls == [FIRST_ISIN]


@pytest.mark.asyncio
async def test_incomplete_cached_snapshot_is_replaced_from_cbonds():
    incomplete = cached(bond_data())
    incomplete.modified_duration = None
    repository = FakeSnapshotRepository([incomplete])
    provider = FakeProvider({FIRST_ISIN: bond_data()})

    result = await MarketDataService(FakeUnitOfWork(repository), provider).resolve_snapshots(
        [FIRST_ISIN], calculation_date=CALCULATION_DATE, last_trading_date=LAST_TRADING_DATE
    )

    assert result[FIRST_ISIN] is repository.added[0]
    assert provider.calls == [FIRST_ISIN]


@pytest.mark.asyncio
async def test_second_call_reuses_snapshot_saved_by_first_call():
    repository = FakeSnapshotRepository()
    provider = FakeProvider({FIRST_ISIN: bond_data()})
    service = MarketDataService(FakeUnitOfWork(repository), provider)

    first = await service.resolve_snapshots(
        [FIRST_ISIN], calculation_date=CALCULATION_DATE, last_trading_date=LAST_TRADING_DATE
    )
    second = await service.resolve_snapshots(
        [FIRST_ISIN], calculation_date=CALCULATION_DATE, last_trading_date=LAST_TRADING_DATE
    )

    assert second[FIRST_ISIN] is first[FIRST_ISIN]
    assert provider.calls == [FIRST_ISIN]
    assert len(repository.added) == 1


@pytest.mark.asyncio
async def test_prepare_snapshots_does_not_write_before_calculation_transaction():
    repository = FakeSnapshotRepository()
    uow = FakeUnitOfWork(repository)
    provider = FakeProvider({FIRST_ISIN: bond_data()})

    prepared = await MarketDataService(uow, provider).prepare_snapshots(
        [FIRST_ISIN, FIRST_ISIN],
        calculation_date=CALCULATION_DATE,
        last_trading_date=LAST_TRADING_DATE,
    )

    assert list(prepared.snapshots) == [FIRST_ISIN]
    assert prepared.new_snapshots == (prepared.snapshots[FIRST_ISIN],)
    assert repository.added == []
    assert uow.commits == 0
    assert provider.calls == [FIRST_ISIN]


@pytest.mark.asyncio
async def test_older_valid_candidate_is_used_when_newer_candidate_is_stale():
    valid = cached(bond_data())
    stale = cached(
        bond_data(quote_date=date(2026, 10, 22), fetched_at=datetime(2026, 10, 25, 8, tzinfo=UTC))
    )
    repository = FakeSnapshotRepository([valid, stale])
    provider = FakeProvider({})

    result = await MarketDataService(FakeUnitOfWork(repository), provider).resolve_snapshots(
        [FIRST_ISIN], calculation_date=CALCULATION_DATE, last_trading_date=LAST_TRADING_DATE
    )

    assert result[FIRST_ISIN] is valid
    assert provider.calls == []


@pytest.mark.asyncio
async def test_repeated_isin_is_loaded_once_but_snapshot_can_be_reused_by_each_line():
    repository = FakeSnapshotRepository()
    provider = FakeProvider({FIRST_ISIN: bond_data()})

    result = await MarketDataService(FakeUnitOfWork(repository), provider).resolve_snapshots(
        [FIRST_ISIN, " ru000a10d4y2 ", FIRST_ISIN],
        calculation_date=CALCULATION_DATE,
        last_trading_date=LAST_TRADING_DATE,
    )

    assert list(result) == [FIRST_ISIN]
    assert provider.calls == [FIRST_ISIN]
    assert len(repository.added) == 1
    assert result[FIRST_ISIN].id is not None


@pytest.mark.asyncio
async def test_only_missing_isin_is_requested_from_cbonds():
    first = cached(bond_data())
    repository = FakeSnapshotRepository([first])
    provider = FakeProvider({SECOND_ISIN: bond_data(SECOND_ISIN)})

    result = await MarketDataService(FakeUnitOfWork(repository), provider).resolve_snapshots(
        [FIRST_ISIN, SECOND_ISIN],
        calculation_date=CALCULATION_DATE,
        last_trading_date=LAST_TRADING_DATE,
    )

    assert result[FIRST_ISIN] is first
    assert result[SECOND_ISIN] is repository.added[0]
    assert provider.calls == [SECOND_ISIN]


@pytest.mark.asyncio
async def test_cbonds_failure_is_preserved_without_rudata_call():
    repository = FakeSnapshotRepository()
    uow = FakeUnitOfWork(repository)
    provider = FakeProvider({FIRST_ISIN: ProviderUnavailableError("Cbonds недоступен")})

    with pytest.raises(ProviderUnavailableError, match="Cbonds недоступен"):
        await MarketDataService(uow, provider).resolve_snapshots(
            [FIRST_ISIN], calculation_date=CALCULATION_DATE, last_trading_date=LAST_TRADING_DATE
        )

    assert repository.added == []
    assert uow.commits == 0


@pytest.mark.asyncio
async def test_stale_provider_response_is_not_cached():
    repository = FakeSnapshotRepository()
    provider = FakeProvider({FIRST_ISIN: bond_data(quote_date=date(2026, 10, 22))})

    with pytest.raises(StaleMarketDataError):
        await MarketDataService(FakeUnitOfWork(repository), provider).resolve_snapshots(
            [FIRST_ISIN], calculation_date=CALCULATION_DATE, last_trading_date=LAST_TRADING_DATE
        )

    assert repository.added == []


@pytest.mark.asyncio
async def test_provider_response_fetched_on_other_moscow_day_is_rejected():
    repository = FakeSnapshotRepository()
    provider = FakeProvider(
        {FIRST_ISIN: bond_data(fetched_at=datetime(2026, 10, 24, 20, tzinfo=UTC))}
    )

    with pytest.raises(StaleMarketDataError, match="день расчёта"):
        await MarketDataService(FakeUnitOfWork(repository), provider).resolve_snapshots(
            [FIRST_ISIN], calculation_date=CALCULATION_DATE, last_trading_date=LAST_TRADING_DATE
        )

    assert repository.added == []


@pytest.mark.asyncio
async def test_provider_data_from_other_source_is_rejected():
    repository = FakeSnapshotRepository()
    provider = FakeProvider({FIRST_ISIN: bond_data(source=MarketDataSource.RUDATA)})

    with pytest.raises(IncompleteMarketDataError, match="источника"):
        await MarketDataService(FakeUnitOfWork(repository), provider).resolve_snapshots(
            [FIRST_ISIN], calculation_date=CALCULATION_DATE, last_trading_date=LAST_TRADING_DATE
        )

    assert repository.added == []


@pytest.mark.asyncio
async def test_empty_input_skips_database_and_provider():
    repository = FakeSnapshotRepository()
    provider = FakeProvider({})

    result = await MarketDataService(FakeUnitOfWork(repository), provider).resolve_snapshots(
        [], calculation_date=CALCULATION_DATE, last_trading_date=LAST_TRADING_DATE
    )

    assert result == {}
    assert repository.lookups == []
    assert provider.calls == []


@pytest.mark.asyncio
async def test_snapshot_repository_filters_by_moscow_date():
    class RecordingSession:
        async def scalars(self, statement):
            self.statement = statement
            return []

    session = RecordingSession()
    result = await SnapshotRepository(session).get_fetched_on_date([FIRST_ISIN], CALCULATION_DATE)

    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    assert result == []
    assert "timezone(" in sql
    assert "instrument_snapshots.fetched_at" in sql
    assert "instrument_snapshots.isin IN" in sql
    assert "ORDER BY instrument_snapshots.fetched_at DESC" in sql
