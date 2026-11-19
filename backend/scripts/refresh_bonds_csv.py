"""Выгрузка реальных флоатеров RUB и закреплённых fixed CNY из MOEX ISS."""

import argparse
import asyncio
import csv
import hashlib
import io
import json
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx

from app.config import get_settings
from app.domain.enums import CouponType, MarketDataSource, PriceType, QuoteKind
from app.domain.market_data import NormalizedBondData
from app.providers.csv import OPTIONAL_COLUMNS, REQUIRED_COLUMNS, CsvBondDataProvider
from app.services.market_data import MOSCOW

ISS = "https://iss.moex.com/iss"
MARKET_URL = f"{ISS}/engines/stock/markets/bonds/securities.json"
FLOATING = "Облигация с плавающим купоном"
FIXED_DETAILS = "Фиксированный с известными купонами"
CALCULATOR_URL = f"{ISS}/apps/bondization/yieldscalculator"
FIXED_CNY_ISINS = ("RU000A10GEU5", "RU000A1054W1", "RU000A10CP52")


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


def normalize_fixed(
    security: dict,
    quote: dict,
    description: dict,
    issuer: dict,
    calculated: dict,
    *,
    trade_date: date,
    fetched_at: datetime,
) -> NormalizedBondData:
    """Цена, НКД и риски fixed из одного ответа калькулятора на одну дату."""
    isin = security["ISIN"]
    currency = security["FACEUNIT"]
    if (
        description.get("ISIN") != isin
        or issuer.get("isin") != isin
        or calculated.get("SECID") != security["SECID"]
        or quote.get("SECID") != security["SECID"]
        or quote.get("BOARDID") != security["BOARDID"]
        or security.get("COUPON_DETAILS") != FIXED_DETAILS
        or currency != "CNY"
        or security["CURRENCYID"] != currency
        or calculated.get("FACEUNIT") != currency
        or calculated.get("COUPONCURRENCYID") != currency
    ):
        raise ValueError("Несогласованный выпуск, купон или валюта fixed")
    if (
        calculated.get("TRADEDATE") != trade_date.isoformat()
        or calculated.get("SETTLEDATE") != trade_date.isoformat()
        or date.fromisoformat(quote["SYSTIME"][:10]) != trade_date
        or quote["NUMTRADES"] <= 0
    ):
        raise ValueError("Цена и риски fixed относятся к другой дате")
    if calculated.get("SELLTYPE") != "MATDATE" or calculated.get("OFFERDATE"):
        raise ValueError("Калькулятор вернул расчёт к оферте вместо погашения")
    if calculated.get("MATDATE") != security["MATDATE"]:
        raise ValueError("Не совпадает дата погашения")
    values = {}
    for name in (
        "FACEVALUE",
        "PRICEPRC",
        "PRICE",
        "PRICEWACCINT",
        "ACCINT",
        "MODIFIEDDURATION",
        "CONVEXITY",
    ):
        try:
            value = Decimal(str(calculated[name]))
        except (KeyError, InvalidOperation) as error:
            raise ValueError(f"Отсутствует числовое поле калькулятора {name}") from error
        if not value.is_finite():
            raise ValueError(f"Некорректное поле калькулятора {name}")
        values[name] = value
    if (
        values["PRICEPRC"] != Decimal(str(quote["LAST"]))
        or values["FACEVALUE"] != Decimal(str(security["FACEVALUE"]))
        or values["PRICE"] != values["FACEVALUE"] * values["PRICEPRC"] / 100
        or values["PRICEWACCINT"] != values["PRICE"] + values["ACCINT"]
    ):
        raise ValueError("Калькулятор использовал другую цену или номинал")
    return NormalizedBondData(
        isin=isin,
        source=MarketDataSource.CSV,
        currency=currency,
        nominal_per_bond=values["FACEVALUE"],
        quote_kind=QuoteKind.AMOUNT,
        quote_value=values["PRICEWACCINT"],
        price_type=PriceType.DIRTY,
        quote_source=(
            f"MOEX ISS {security['BOARDID']}; yieldscalculator BY_PRICE_TO_MATURITY; "
            f"valuation={trade_date}"
        ),
        quote_as_of_date=trade_date,
        coupon_type=CouponType.FIXED,
        fetched_at=fetched_at,
        accrued_per_bond=values["ACCINT"],
        accrued_as_of_date=trade_date,
        coupon_frequency=int(description["COUPONFREQUENCY"]),
        modified_duration=values["MODIFIEDDURATION"],
        convexity=values["CONVEXITY"],
        risk_as_of_date=date.fromisoformat(calculated["TRADEDATE"]),
        provider_instrument_id=security["SECID"],
        issue_name=security["SECNAME"],
        issuer_name=issuer.get("emitent_title") or None,
    )


async def export_csv(
    output: Path,
    count: int,
    client: httpx.AsyncClient,
    *,
    add_fixed: bool = False,
) -> dict:
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
    securities = records(document, "securities")
    candidates = []
    for security in securities:
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

    async def complete(security: dict, quote: dict, *, fixed: bool = False):
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
            calculator_params = {
                "secid": secid,
                "tradedate": trade_date.isoformat(),
                "calc_method": "BY_PRICE_TO_MATURITY",
                "calc_value": str(quote["LAST"]),
            }
            calculation = await fetch(CALCULATOR_URL, **calculator_params) if fixed else None
            if fixed:
                bond = normalize_fixed(
                    security,
                    quote,
                    description,
                    issuer,
                    calculation["calculated"],
                    trade_date=trade_date,
                    fetched_at=fetched_at,
                )
            else:
                bond = normalize_floater(
                    security,
                    quote,
                    description,
                    issuer,
                    trade_date=trade_date,
                    fetched_at=fetched_at,
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
            if fixed:
                evidence["calculation"] = calculation
                evidence["calculation_request"] = calculator_params
                evidence["urls"].append(CALCULATOR_URL)
            return bond, evidence

    selected: dict[str, tuple[NormalizedBondData, dict]] = {}
    floating_downloaded_at = fetched_at
    if add_fixed:
        previous_metadata = json.loads(output.with_suffix(".meta.json").read_text(encoding="utf-8"))
        if previous_metadata["market_trade_date"] != trade_date.isoformat():
            raise ValueError("Старый CSV относится к другой дате. Выполните полное обновление.")
        previous_source = json.loads(output.with_suffix(".source.json").read_text(encoding="utf-8"))
        previous = await CsvBondDataProvider(
            output,
            source=MarketDataSource.CSV,
            require_manifest=True,
        ).list_bonds()
        selected = {
            bond.isin: (bond, previous_source[bond.isin])
            for bond in previous
            if bond.coupon_type is CouponType.FLOATING
        }
        if len(selected) != count:
            raise ValueError("Число флоатеров в прежнем CSV отличается от --count")
        floating_downloaded_at = datetime.fromisoformat(previous_metadata["downloaded_at"])
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
    # Эти fixed-выпуски обновляются при каждом запуске, а не исчезают из CSV завтра.
    for isin in FIXED_CNY_ISINS:
        security = next(
            (row for row in securities if row["ISIN"] == isin and row["BOARDID"] == "TQOY"), None
        )
        if security is None:
            raise ValueError(f"Нет валютного режима TQOY для {isin}; CSV не изменён")
        quote = quotes[(security["SECID"], security["BOARDID"])]
        bond, evidence = await complete(security, quote, fixed=True)
        selected[bond.isin] = bond, evidence
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
        "downloaded_at": min(floating_downloaded_at, fetched_at).isoformat(),
        "updated_at": fetched_at.isoformat(),
        "floating_downloaded_at": floating_downloaded_at.isoformat(),
        "market_trade_date": trade_date.isoformat(),
        "calculation_date": fetched_at.astimezone(MOSCOW).date().isoformat(),
        "count": len(selected),
        "floating_count": count,
        "fixed_isins": list(FIXED_CNY_ISINS),
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "selection": (
            "RUB floating coupon; TQCB/TQOB; turnover descending; "
            "plus pinned fixed CNY issues on TQOY; trades on market_trade_date"
        ),
        "price_method": (
            "dirty amount = nominal on settlement * LAST / 100 + ACCRUEDINT on SETTLEDATE"
        ),
        "risk_method": (
            "floating: 1/COUPONFREQUENCY and 0 (TradeMetric); "
            "fixed: MODIFIEDDURATION and CONVEXITY from MOEX yieldscalculator"
        ),
        "fixed_price_method": (
            "PRICEWACCINT and ACCINT from calculator on TRADEDATE (T+0 valuation)"
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
    parser.add_argument(
        "--add-fixed",
        action="store_true",
        help="сохранить прежние флоатеры и добавить/обновить три fixed CNY",
    )
    args = parser.parse_args()
    if not 1 <= args.count <= 1000:
        parser.error("--count должен быть в диапазоне 1..1000")
    settings = get_settings()
    output = args.output or settings.resolved_csv_path
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        metadata = await export_csv(output, args.count, client, add_fixed=args.add_fixed)
    print(f"Saved {metadata['count']} real ISINs to {output}")
    print(f"Market date: {metadata['market_trade_date']}; updated: {metadata['updated_at']}")


if __name__ == "__main__":
    asyncio.run(main())
