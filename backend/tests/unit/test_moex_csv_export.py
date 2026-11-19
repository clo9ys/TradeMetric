import copy
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.domain.enums import MarketDataSource
from app.domain.errors import IncompleteMarketDataError, StaleMarketDataError
from app.providers.csv import CsvBondDataProvider
from app.services.calculation import calculate_trade_metrics
from scripts.refresh_bonds_csv import export_csv, normalize_floater

DATA = Path(__file__).resolve().parents[2] / "data/bonds_market.csv"
META = json.loads(DATA.with_suffix(".meta.json").read_text(encoding="utf-8"))
NOW = datetime.fromisoformat(META["downloaded_at"])
EVIDENCE = json.loads(DATA.with_suffix(".source.json").read_text(encoding="utf-8"))


async def test_100_real_isins_match_source_and_calculate_without_placeholders():
    provider = CsvBondDataProvider(
        DATA, source=MarketDataSource.CSV, clock=lambda: NOW, require_manifest=True
    )
    bonds = await provider.list_bonds()
    assert len(bonds) == len({bond.isin for bond in bonds}) == 100
    assert hashlib.sha256(DATA.read_bytes()).hexdigest() == META["csv_sha256"]
    for bond in bonds:
        source = EVIDENCE[bond.isin]
        expected = normalize_floater(
            source["security"],
            source["quote"],
            source["description"],
            source["issuer"],
            trade_date=bond.quote_as_of_date,
            fetched_at=NOW,
        )
        assert bond == expected
        bond.validate_freshness(
            calculation_date=NOW.date(), last_trading_date=bond.quote_as_of_date
        )
        assert bond.accrued_per_bond is None  # Полная цена уже содержит НКД.
        assert bond.modified_duration is None and bond.convexity is None
        long = calculate_trade_metrics(bond, 3, Decimal(1))
        short = calculate_trade_metrics(bond, -3, Decimal(1))
        assert long.dirty_price_per_bond == bond.quote_value
        assert long.dv01_rub + short.dv01_rub == 0
        assert long.convexity_used == 0


async def test_reading_old_market_file_does_not_make_it_fresh():
    provider = CsvBondDataProvider(
        DATA,
        source=MarketDataSource.CSV,
        clock=lambda: NOW + timedelta(days=1),
        require_manifest=True,
    )
    with pytest.raises(StaleMarketDataError, match="не сегодня"):
        await provider.list_bonds()


@pytest.mark.parametrize(
    "change",
    [
        {"source": "unknown"},
        {"csv_sha256": "wrong"},
        {"count": 99},
        {"market_trade_date": "2099-01-01"},
        {"downloaded_at": "2099-01-01T10:00:00+00:00"},
    ],
)
async def test_broken_manifest_is_rejected(tmp_path, change):
    path = tmp_path / "bonds.csv"
    path.write_bytes(DATA.read_bytes())
    path.with_suffix(".meta.json").write_text(json.dumps(META | change), encoding="utf-8")
    with pytest.raises(IncompleteMarketDataError):
        await CsvBondDataProvider(path, require_manifest=True, clock=lambda: NOW).list_bonds()


@pytest.mark.parametrize(
    "section,changes",
    [
        ("quote", {"NUMTRADES": 0}),
        ("quote", {"SYSTIME": "2000-01-01 12:00:00"}),
        ("description", {"BOND_TYPE": "Облигация с фиксированным (известным) купоном"}),
        ("description", {"ISIN": "wrong"}),
        ("security", {"ACCRUEDINT": "NaN"}),
        ("description", {"COUPONFREQUENCY": "2.5"}),
        ("quote", {"LAST": "0"}),
    ],
)
def test_bad_exchange_record_is_not_patched_with_invented_values(section, changes):
    source = copy.deepcopy(next(iter(EVIDENCE.values())))
    source[section].update(changes)
    with pytest.raises((ValueError, IncompleteMarketDataError)):
        normalize_floater(
            source["security"],
            source["quote"],
            source["description"],
            source["issuer"],
            trade_date=NOW.date(),
            fetched_at=NOW,
        )


async def test_incomplete_export_does_not_overwrite_existing_file(tmp_path):
    target = tmp_path / "bonds.csv"
    target.write_text("previous snapshot", encoding="utf-8")
    document = {
        "dataversion": {"columns": ["trade_date"], "data": [["2026-11-19"]]},
        "securities": {"columns": [], "data": []},
        "marketdata": {"columns": [], "data": []},
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=document))
    ) as client:
        with pytest.raises(ValueError, match="Существующий CSV не изменён"):
            await export_csv(target, 100, client)
    assert target.read_text(encoding="utf-8") == "previous snapshot"
