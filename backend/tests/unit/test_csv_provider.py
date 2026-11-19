import csv
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.config import Settings
from app.domain.enums import MarketDataSource
from app.domain.errors import (
    IncompleteMarketDataError,
    InstrumentNotFoundError,
    ProviderUnavailableError,
    StaleMarketDataError,
)
from app.providers.csv import CsvBondDataProvider
from app.providers.factory import build_bond_provider
from app.services.market_data import MarketDataService
from tests.unit.test_market_data_service import FakeSnapshotRepository, FakeUnitOfWork

SAMPLE = Path(__file__).resolve().parents[2] / "data/bonds_demo.csv"
NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)
DAY = NOW.date()
ISIN = "RUDEMO000016"


def write_csv(tmp_path, *, change=None, duplicate=False):
    with SAMPLE.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames
        rows = list(reader)
    if change:
        change(rows)
    if duplicate:
        rows.append(rows[0] | {"isin": " rudemo000016 "})
    path = tmp_path / "bonds.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


async def test_csv_normalizes_fixed_floating_and_preserves_market_dates():
    provider = CsvBondDataProvider(SAMPLE, clock=lambda: NOW)
    fixed = await provider.get_bond(" rudemo000016 ")
    floating = await provider.get_bond("RUDEMO000032")
    assert fixed.nominal_per_bond == Decimal("1000")
    assert fixed.quote_value == Decimal("101.25")
    assert fixed.source is MarketDataSource.DEMO
    assert fixed.fetched_at == NOW
    assert fixed.quote_as_of_date == fixed.risk_as_of_date == DAY
    assert floating.coupon_frequency == 4
    assert floating.modified_duration is None
    assert await provider.get_bond(ISIN) is fixed


@pytest.mark.parametrize(
    "field,value",
    [
        ("quote_value", "oops"),
        ("quote_value", "NaN"),
        ("quote_value", "Infinity"),
        ("quote_value", "101,25"),
        ("nominal_per_bond", ""),
        ("quote_source", ""),
        ("quote_as_of_date", ""),
        ("quote_as_of_date", "2026-99-99"),
        ("currency", ""),
        ("currency", "usd"),
        ("isin", "invalid"),
        ("price_type", "unknown"),
        ("modified_duration", ""),
        ("convexity", ""),
        ("risk_as_of_date", ""),
        ("accrued_per_bond", ""),
        ("accrued_as_of_date", ""),
        ("coupon_frequency", "4.0"),
    ],
)
async def test_invalid_csv_is_rejected_with_line_number(tmp_path, field, value):
    path = write_csv(tmp_path, change=lambda rows: rows[0].update({field: value}))
    with pytest.raises(IncompleteMarketDataError, match="строка 2"):
        await CsvBondDataProvider(path, clock=lambda: NOW).get_bond(ISIN)


async def test_invalid_later_row_rejects_whole_file(tmp_path):
    path = write_csv(tmp_path, change=lambda rows: rows[2].update(coupon_frequency=""))
    with pytest.raises(IncompleteMarketDataError, match="строка 4"):
        await CsvBondDataProvider(path, clock=lambda: NOW).get_bond(ISIN)


async def test_duplicate_isin_is_rejected_even_if_normalization_matches(tmp_path):
    path = write_csv(tmp_path, duplicate=True)
    with pytest.raises(IncompleteMarketDataError, match="повторный ISIN"):
        await CsvBondDataProvider(path).get_bond(ISIN)


async def test_missing_isin_and_missing_file_have_distinct_errors(tmp_path):
    with pytest.raises(InstrumentNotFoundError, match="XS0157815647"):
        await CsvBondDataProvider(SAMPLE).get_bond("XS0157815647")
    with pytest.raises(ProviderUnavailableError, match="прочитать CSV"):
        await CsvBondDataProvider(tmp_path / "missing.csv").get_bond(ISIN)


@pytest.mark.parametrize(
    "contents",
    [
        "",
        "isin,isin\na,b\n",
        "isin\nRUDEMO000016\n",
        SAMPLE.read_text(encoding="utf-8-sig").splitlines()[0] + "\n",
        SAMPLE.read_text(encoding="utf-8-sig") + '"unclosed',
        SAMPLE.read_text(encoding="utf-8-sig").replace("RUB,1000", "RUB,1000,extra", 1),
    ],
)
async def test_broken_csv_shape_is_rejected(tmp_path, contents):
    path = tmp_path / "broken.csv"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(IncompleteMarketDataError):
        await CsvBondDataProvider(path).get_bond(ISIN)


async def test_reading_old_csv_today_does_not_refresh_market_dates():
    tomorrow = datetime(2026, 11, 20, 12, tzinfo=UTC)
    provider = CsvBondDataProvider(SAMPLE, clock=lambda: tomorrow)
    service = MarketDataService(
        FakeUnitOfWork(FakeSnapshotRepository()), provider, source=MarketDataSource.DEMO
    )
    with pytest.raises(StaleMarketDataError, match="Котировка"):
        await service.prepare_snapshots(
            [ISIN], calculation_date=tomorrow.date(), last_trading_date=tomorrow.date()
        )
    bond = await provider.get_bond(ISIN)
    assert bond.fetched_at == tomorrow
    assert bond.quote_as_of_date == DAY


@pytest.mark.parametrize("source", [MarketDataSource.DEMO, MarketDataSource.CSV])
async def test_selected_csv_source_is_loaded_once_and_then_cached(source):
    repo = FakeSnapshotRepository()
    provider = CsvBondDataProvider(SAMPLE, source=source, clock=lambda: NOW)
    service = MarketDataService(FakeUnitOfWork(repo), provider, source=source)
    first = await service.resolve_snapshots(
        [ISIN, ISIN], calculation_date=DAY, last_trading_date=DAY
    )
    second = await service.resolve_snapshots([ISIN], calculation_date=DAY, last_trading_date=DAY)
    assert len(repo.added) == 1
    assert first[ISIN] is second[ISIN]
    assert first[ISIN].source == source.value


def test_config_selects_source_and_resolves_path_from_repository():
    settings = Settings(
        _env_file=None, postgres_user="test", postgres_password="test", postgres_db="test"
    )
    provider, source = build_bond_provider(settings)
    assert source is MarketDataSource.DEMO
    assert settings.resolved_csv_path == SAMPLE
    provider, source = build_bond_provider(settings.model_copy(update={"csv_data_mode": "market"}))
    assert provider.source is source is MarketDataSource.CSV
    provider, source = build_bond_provider(
        settings.model_copy(update={"bond_data_source": "cbonds"})
    )
    assert source is MarketDataSource.CBONDS


async def test_market_csv_cannot_reuse_demo_cache():
    from app.services.market_data import _to_snapshot

    demo_provider = CsvBondDataProvider(SAMPLE, source=MarketDataSource.DEMO, clock=lambda: NOW)
    demo_snapshot = _to_snapshot(await demo_provider.get_bond(ISIN))
    repo = FakeSnapshotRepository([demo_snapshot])
    provider = CsvBondDataProvider(SAMPLE, source=MarketDataSource.CSV, clock=lambda: NOW)
    service = MarketDataService(FakeUnitOfWork(repo), provider, source=MarketDataSource.CSV)
    prepared = await service.prepare_snapshots([ISIN], calculation_date=DAY, last_trading_date=DAY)
    assert prepared.snapshots[ISIN] is not demo_snapshot
    assert prepared.snapshots[ISIN].source == "csv"
    assert len(prepared.new_snapshots) == 1


async def test_missing_second_isin_does_not_save_first_snapshot():
    repo = FakeSnapshotRepository()
    uow = FakeUnitOfWork(repo)
    provider = CsvBondDataProvider(SAMPLE, clock=lambda: NOW)
    service = MarketDataService(uow, provider, source=MarketDataSource.DEMO)
    with pytest.raises(InstrumentNotFoundError):
        await service.resolve_snapshots(
            [ISIN, "XS0157815647"], calculation_date=DAY, last_trading_date=DAY
        )
    assert repo.added == []
    assert uow.commits == 0
