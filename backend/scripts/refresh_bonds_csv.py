"""Выгрузка реальных флоатеров MOEX ISS в CSV для CsvBondDataProvider."""

import argparse
import asyncio
import csv
import hashlib
import io
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import httpx

from app.config import get_settings
from app.domain.enums import CouponType, MarketDataSource, PriceType, QuoteKind
from app.domain.market_data import NormalizedBondData
from app.providers.csv import OPTIONAL_COLUMNS, REQUIRED_COLUMNS
from app.services.market_data import MOSCOW

ISS = "https://iss.moex.com/iss"
MARKET_URL = f"{ISS}/engines/stock/markets/bonds/securities.json"
FLOATING = "Облигация с плавающим купоном"


def records(document: dict, block: str) -> list[dict]:
    table = document[block]
    return [dict(zip(table["columns"], row, strict=True)) for row in table["data"]]


def normalize_floater(
    security: dict,
    quote: dict,
    description: dict,
    issuer: dict,
    *,
    trade_date: date,
    fetched_at: datetime,
) -> NormalizedBondData:
    """Полная цена T+1 из LAST (%) и ACCRUEDINT, без выдуманных риск-параметров."""
    isin = security["ISIN"]
    if (
        description.get("ISIN") != isin
        or issuer.get("isin") != isin
        or quote["SECID"] != security["SECID"]
        or quote["BOARDID"] != security["BOARDID"]
        or description.get("BOND_TYPE") != FLOATING
        or security["BONDTYPE"] != FLOATING
    ):
        raise ValueError("Данные выпуска, купона или котировки не согласованы")
    if date.fromisoformat(quote["SYSTIME"][:10]) != trade_date or quote["NUMTRADES"] <= 0:
        raise ValueError("Нет сделок на дату торгов")
    if security["CURRENCYID"] != "SUR" or security["FACEUNIT"] != "SUR":
        raise ValueError("В этой выгрузке используются рублёвые облигации")
    settlement_date = date.fromisoformat(security["SETTLEDATE"])
    if settlement_date < trade_date:
        raise ValueError("Дата расчётов раньше даты торгов")
    nominal = Decimal(str(security.get("FACEVALUEONSETTLEDATE") or security["FACEVALUE"]))
    clean_percent = Decimal(str(quote["LAST"]))
    accrued = Decimal(str(security["ACCRUEDINT"]))
    if (
        not accrued.is_finite()
        or accrued < 0
        or not clean_percent.is_finite()
        or clean_percent <= 0
    ):
        raise ValueError("Некорректная цена или НКД")
    frequency_text = description["COUPONFREQUENCY"]
    frequency = int(frequency_text)
    if Decimal(str(frequency_text)) != frequency:
        raise ValueError("Частота купона должна быть целым числом")
    dirty_price = nominal * clean_percent / Decimal(100) + accrued
    return NormalizedBondData(
        isin=isin,
        source=MarketDataSource.CSV,
        currency="RUB",
        nominal_per_bond=nominal,
        quote_kind=QuoteKind.AMOUNT,
        quote_value=dirty_price,
        price_type=PriceType.DIRTY,
        quote_source=(
            f"MOEX ISS {security['BOARDID']}; LAST percent + ACCRUEDINT; "
            f"settlement={settlement_date}"
        ),
        quote_as_of_date=trade_date,
        coupon_type=CouponType.FLOATING,
        coupon_frequency=frequency,
        fetched_at=fetched_at,
        provider_instrument_id=security["SECID"],
        issue_name=security["SECNAME"],
        issuer_name=issuer.get("emitent_title") or None,
    )


async def export_csv(output: Path, count: int, client: httpx.AsyncClient) -> dict:
    async def fetch(url: str, **params) -> dict:
        response = await client.get(url, params={"iss.meta": "off", **params})
        response.raise_for_status()
        return response.json(parse_float=Decimal)

    document = await fetch(MARKET_URL)
    fetched_at = datetime.now(UTC)
    trade_date = date.fromisoformat(records(document, "dataversion")[0]["trade_date"])
    if trade_date > fetched_at.astimezone(MOSCOW).date():
        raise ValueError("Биржа вернула будущую дату торгов")
    quotes = {(q["SECID"], q["BOARDID"]): q for q in records(document, "marketdata")}
    candidates = []
    for security in records(document, "securities"):
        quote = quotes.get((security["SECID"], security["BOARDID"]))
        if (
            security["BOARDID"] in ("TQCB", "TQOB")
            and security["BONDTYPE"] == FLOATING
            and security["FACEUNIT"] == security["CURRENCYID"] == "SUR"
            and quote
            and quote["LAST"] is not None
            and quote["NUMTRADES"] > 0
        ):
            candidates.append((security, quote))
    candidates.sort(key=lambda pair: Decimal(str(pair[1].get("VALTODAY") or 0)), reverse=True)
    semaphore = asyncio.Semaphore(4)

    async def complete(security: dict, quote: dict):
        async with semaphore:
            secid = security["SECID"]
            details = await fetch(f"{ISS}/securities/{secid}.json")
            description = {row["name"]: row["value"] for row in records(details, "description")}
            search = await fetch(f"{ISS}/securities.json", q=security["ISIN"])
            issuer = next(
                row
                for row in records(search, "securities")
                if row["isin"] == security["ISIN"] and row["secid"] == secid
            )
            bond = normalize_floater(
                security, quote, description, issuer, trade_date=trade_date, fetched_at=fetched_at
            )
            evidence = {
                "security": security,
                "quote": quote,
                "description": description,
                "issuer": issuer,
                "urls": [
                    MARKET_URL,
                    f"{ISS}/securities/{secid}.json",
                    f"{ISS}/securities.json?q={security['ISIN']}",
                ],
            }
            return bond, evidence

    selected: dict[str, tuple[NormalizedBondData, dict]] = {}
    rejected: list[str] = []
    # Небольшие пачки: не запрашиваем карточки для всех бумаг биржи.
    cursor = 0
    while cursor < len(candidates) and len(selected) < count:
        batch = candidates[cursor : cursor + min(20, count - len(selected))]
        cursor += len(batch)
        results = await asyncio.gather(*(complete(*pair) for pair in batch), return_exceptions=True)
        for pair, result in zip(batch, results, strict=True):
            if isinstance(result, BaseException):
                rejected.append(f"{pair[0]['ISIN']}: {type(result).__name__}: {result}")
            else:
                bond, evidence = result
                selected.setdefault(bond.isin, (bond, evidence))
        if len(selected) == count:
            break
    if len(selected) != count:
        raise ValueError(
            f"Найдено только {len(selected)} полных выпусков из {count}. "
            "Существующий CSV не изменён; пропуски не заполняются синтетическими значениями."
        )
    stream = io.StringIO(newline="")
    columns = sorted(REQUIRED_COLUMNS) + sorted(OPTIONAL_COLUMNS)
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for bond, _ in selected.values():
        fields = {
            name: value.value if hasattr(value, "value") else value
            for name in columns
            if (value := getattr(bond, name)) is not None
        }
        writer.writerow(fields)
    csv_bytes = stream.getvalue().encode("utf-8")
    metadata = {
        "source": "MOEX ISS",
        "downloaded_at": fetched_at.isoformat(),
        "market_trade_date": trade_date.isoformat(),
        "calculation_date": fetched_at.astimezone(MOSCOW).date().isoformat(),
        "count": count,
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "selection": (
            "RUB floating coupon; TQCB/TQOB; trades on market_trade_date; turnover descending"
        ),
        "price_method": (
            "dirty amount = nominal on settlement * LAST / 100 + ACCRUEDINT on SETTLEDATE"
        ),
        "risk_method": (
            "floating: modified_duration=1/COUPONFREQUENCY; convexity=0 (TradeMetric methodology)"
        ),
        "rejected": rejected,
    }
    evidence = {isin: value[1] for isin, value in selected.items()}
    output.parent.mkdir(parents=True, exist_ok=True)
    files = {
        output: csv_bytes,
        output.with_suffix(".meta.json"): json.dumps(
            metadata, ensure_ascii=False, indent=2
        ).encode(),
        output.with_suffix(".source.json"): json.dumps(
            evidence, ensure_ascii=False, indent=2, default=str
        ).encode(),
    }
    for path, data in files.items():
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
    return metadata


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.count <= 1000:
        parser.error("--count должен быть в диапазоне 1..1000")
    settings = get_settings()
    output = args.output or settings.resolved_csv_path
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        metadata = await export_csv(output, args.count, client)
    print(f"Saved {metadata['count']} real ISINs to {output}")
    print(f"Market date: {metadata['market_trade_date']}; downloaded: {metadata['downloaded_at']}")


if __name__ == "__main__":
    asyncio.run(main())
