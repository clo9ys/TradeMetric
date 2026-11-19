import copy
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.domain.enums import CouponType, MarketDataSource
from app.domain.errors import IncompleteMarketDataError, StaleMarketDataError
from app.providers.csv import CsvBondDataProvider
from app.services.calculation import calculate_trade_metrics
from scripts.refresh_bonds_csv import (
    FIXED_CNY_ISINS,
    export_csv,
    normalize_fixed,
    normalize_floater,
)

DATA = Path(__file__).resolve().parents[2] / "data/bonds_market.csv"
META = json.loads(DATA.with_suffix(".meta.json").read_text(encoding="utf-8"))
NOW = datetime.fromisoformat(META["downloaded_at"])
EVIDENCE = json.loads(DATA.with_suffix(".source.json").read_text(encoding="utf-8"))


async def test_real_floating_and_fixed_isins_match_source_and_calculate():
    provider = CsvBondDataProvider(
        DATA, source=MarketDataSource.CSV, clock=lambda: NOW, require_manifest=True
    )
    bonds = await provider.list_bonds()
    assert len(bonds) == len({bond.isin for bond in bonds}) == 103
    assert sum(bond.coupon_type is CouponType.FLOATING for bond in bonds) == 100
    assert {bond.isin for bond in bonds if bond.coupon_type is CouponType.FIXED} == set(
        FIXED_CNY_ISINS
    )
    assert hashlib.sha256(DATA.read_bytes()).hexdigest() == META["csv_sha256"]
    for bond in bonds:
        source = EVIDENCE[bond.isin]
        fields = [source["security"], source["quote"], source["description"], source["issuer"]]
        if bond.coupon_type is CouponType.FIXED:
            expected = normalize_fixed(
                *fields,
                source["calculation"]["calculated"],
                trade_date=bond.quote_as_of_date,
                fetched_at=NOW,
            )
            assert bond.risk_as_of_date == bond.accrued_as_of_date == bond.quote_as_of_date
            assert bond.modified_duration is not None and bond.convexity is not None
        else:
            expected = normalize_floater(*fields, trade_date=bond.quote_as_of_date, fetched_at=NOW)
            assert bond.accrued_per_bond is None  # Полная цена уже содержит НКД T+1.
            assert bond.modified_duration is None and bond.convexity is None
        assert bond == expected
        bond.validate_freshness(
            calculation_date=NOW.date(), last_trading_date=bond.quote_as_of_date
        )
        long = calculate_trade_metrics(bond, 3, Decimal(1))
        short = calculate_trade_metrics(bond, -3, Decimal(1))
        assert long.dirty_price_per_bond == bond.quote_value
        assert long.dv01_rub + short.dv01_rub == 0
        assert long.convexity_used == (bond.convexity or Decimal(0))


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


@pytest.mark.parametrize(
    "changes",
    [
        {"MODIFIEDDURATION": None},
        {"CONVEXITY": "NaN"},
        {"MODIFIEDDURATION": "-1"},
        {"SECID": "wrong"},
        {"TRADEDATE": "2000-01-01"},
        {"SETTLEDATE": "2000-01-01"},
        {"FACEUNIT": "RUB"},
        {"PRICEPRC": "1"},
        {"PRICEWACCINT": "1"},
        {"OFFERDATE": "2027-01-01"},
    ],
)
def test_fixed_rejects_incomplete_or_misaligned_calculator_result(changes):
    source = EVIDENCE[FIXED_CNY_ISINS[0]]
    calculated = source["calculation"]["calculated"] | changes
    with pytest.raises((ValueError, IncompleteMarketDataError)):
        normalize_fixed(
            source["security"],
            source["quote"],
            source["description"],
            source["issuer"],
            calculated,
            trade_date=NOW.date(),
            fetched_at=NOW,
        )


async def test_refresh_keeps_pinned_fixed_issues_and_records_calculator_provenance(tmp_path):
    floating = next(value for value in EVIDENCE.values() if "calculation" not in value)
    evidence = [floating, *(EVIDENCE[isin] for isin in FIXED_CNY_ISINS)]
    requests = []

    def table(rows):
        columns = list(rows[0])
        return {"columns": columns, "data": [[row.get(key) for key in columns] for row in rows]}

    def respond(request):
        requests.append(request)
        if request.url.path.endswith("/markets/bonds/securities.json"):
            doc = {
                "dataversion": table([{"trade_date": META["market_trade_date"]}]),
                "securities": table([row["security"] for row in evidence]),
                "marketdata": table([row["quote"] for row in evidence]),
            }
        elif request.url.path.endswith("/yieldscalculator"):
            isin = request.url.params["secid"]
            assert request.url.params["calc_method"] == "BY_PRICE_TO_MATURITY"
            assert request.url.params["calc_value"] == str(EVIDENCE[isin]["quote"]["LAST"])
            doc = EVIDENCE[isin]["calculation"]
        elif request.url.path.endswith("/securities.json"):
            row = next(
                row for row in evidence if row["security"]["ISIN"] == request.url.params["q"]
            )
            doc = {"securities": table([row["issuer"]])}
        else:
            secid = request.url.path.rsplit("/", 1)[-1].removesuffix(".json")
            row = next(row for row in evidence if row["security"]["SECID"] == secid)
            doc = {
                "description": table(
                    [{"name": key, "value": value} for key, value in row["description"].items()]
                )
            }
        return httpx.Response(200, content=json.dumps(doc).encode())

    output = tmp_path / "market.csv"
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        metadata = await export_csv(output, 1, client)
    assert metadata["count"] == 4
    assert metadata["fixed_isins"] == list(FIXED_CNY_ISINS)
    assert len([req for req in requests if req.url.path.endswith("/yieldscalculator")]) == 3
    rows = await CsvBondDataProvider(output).list_bonds()
    assert {bond.isin for bond in rows if bond.currency == "CNY"} == set(FIXED_CNY_ISINS)
