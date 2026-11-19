import asyncio
import csv
import hashlib
import io
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.domain.enums import CouponType, MarketDataSource, PriceType, QuoteKind
from app.domain.errors import (
    IncompleteMarketDataError,
    InstrumentNotFoundError,
    InvalidISINError,
    ProviderUnavailableError,
    StaleMarketDataError,
)
from app.domain.isin import validate_isin
from app.domain.market_data import NormalizedBondData

REQUIRED_COLUMNS = {
    "isin",
    "currency",
    "nominal_per_bond",
    "quote_kind",
    "quote_value",
    "price_type",
    "quote_source",
    "quote_as_of_date",
    "coupon_type",
    "accrued_per_bond",
    "accrued_as_of_date",
    "coupon_frequency",
    "modified_duration",
    "convexity",
    "risk_as_of_date",
}
OPTIONAL_COLUMNS = {"issue_name", "issuer_name", "provider_instrument_id"}


class CsvBondDataProvider:
    """Читает один CSV целиком; ошибочный файл не используется частично."""

    def __init__(
        self,
        path: Path,
        *,
        source: MarketDataSource = MarketDataSource.DEMO,
        clock: Callable[[], datetime] | None = None,
        require_manifest: bool = False,
    ) -> None:
        if source not in (MarketDataSource.CSV, MarketDataSource.DEMO):
            raise ValueError("Источник CSV должен быть csv или demo")
        self._path = path
        self.source = source
        self._clock = clock or (lambda: datetime.now(UTC))
        self._require_manifest = require_manifest
        self._bonds: dict[str, NormalizedBondData] | None = None

    async def get_bond(self, isin: str) -> NormalizedBondData:
        isin = validate_isin(isin)
        await self.list_bonds()
        try:
            return self._bonds[isin]
        except KeyError as error:
            raise InstrumentNotFoundError(f"CSV не содержит ISIN {isin}") from error

    async def list_bonds(self) -> tuple[NormalizedBondData, ...]:
        """Возвращает проверенный каталог CSV без изменения рыночных дат."""
        if self._bonds is None:
            # Файловое чтение выполняется в потоке и не блокирует event loop FastAPI.
            self._bonds = await asyncio.to_thread(self._read)
        return tuple(self._bonds.values())

    def _read(self) -> dict[str, NormalizedBondData]:
        fetched_at = self._clock()
        bonds: dict[str, NormalizedBondData] = {}
        try:
            content = self._path.read_bytes()
            metadata = (
                self._validate_manifest(content, fetched_at) if self._require_manifest else None
            )
            with io.StringIO(content.decode("utf-8-sig"), newline="") as file:
                reader = csv.DictReader(file, strict=True)
                columns = reader.fieldnames or []
                if (
                    not REQUIRED_COLUMNS.issubset(columns)
                    or set(columns) - REQUIRED_COLUMNS - OPTIONAL_COLUMNS
                    or len(columns) != len(set(columns))
                ):
                    raise IncompleteMarketDataError(
                        "CSV: неверный набор колонок или дубли заголовков"
                    )
                for row in reader:
                    try:
                        if None in row or any(value is None for value in row.values()):
                            raise ValueError("число ячеек не соответствует заголовку")
                        cells = {key: value.strip() for key, value in row.items()}
                        bond = self._normalize(cells, fetched_at)
                        if bond.isin in bonds:
                            raise ValueError(f"повторный ISIN {bond.isin}")
                        bonds[bond.isin] = bond
                    except (
                        ValueError,
                        InvalidOperation,
                        InvalidISINError,
                        IncompleteMarketDataError,
                    ) as error:
                        raise IncompleteMarketDataError(
                            f"CSV, строка {reader.line_num}: {error}"
                        ) from error
        except (OSError, UnicodeError) as error:
            raise ProviderUnavailableError(f"Не удалось прочитать CSV {self._path.name}") from error
        except csv.Error as error:
            raise IncompleteMarketDataError(f"Некорректный формат CSV: {error}") from error
        if not bonds:
            raise IncompleteMarketDataError("CSV не содержит облигаций")
        if metadata and (
            len(bonds) != metadata["count"]
            or any(
                bond.quote_as_of_date.isoformat() != metadata["market_trade_date"]
                for bond in bonds.values()
            )
        ):
            raise IncompleteMarketDataError(
                "CSV не соответствует дате или числу выпусков в метаданных"
            )
        return bonds

    def _validate_manifest(self, content: bytes, fetched_at: datetime) -> dict:
        """Чтение старого файла не превращает рыночную выгрузку в свежую."""
        try:
            metadata = json.loads(self._path.with_suffix(".meta.json").read_text(encoding="utf-8"))
            downloaded_at = datetime.fromisoformat(metadata["downloaded_at"])
            if downloaded_at.tzinfo is None or downloaded_at.utcoffset() is None:
                raise ValueError("Нет часового пояса загрузки")
            if downloaded_at > fetched_at:
                raise ValueError("Время загрузки находится в будущем")
            moscow = timezone(timedelta(hours=3))
            if downloaded_at.astimezone(moscow).date() != fetched_at.astimezone(moscow).date():
                raise StaleMarketDataError(
                    "Рыночный CSV загружен не сегодня. Обновите данные: "
                    "python -m scripts.refresh_bonds_csv"
                )
            if metadata["csv_sha256"] != hashlib.sha256(content).hexdigest():
                raise ValueError("Контрольная сумма CSV не совпадает")
            if metadata["source"] != "MOEX ISS":
                raise ValueError("Неизвестный источник выгрузки")
            if (
                date.fromisoformat(metadata["market_trade_date"])
                > fetched_at.astimezone(moscow).date()
            ):
                raise ValueError("Дата торгов находится в будущем")
            if type(metadata["count"]) is not int or metadata["count"] <= 0:
                raise ValueError("Некорректное число выпусков")
            return metadata
        except (OSError, KeyError, ValueError, TypeError) as error:
            raise IncompleteMarketDataError(
                "Нет корректных метаданных рыночного CSV. Обновите выгрузку."
            ) from error

    def _normalize(self, row: dict[str, str], fetched_at: datetime) -> NormalizedBondData:
        def parse(name: str, convert: Callable[[str], object]) -> object:
            try:
                return convert(row[name])
            except (ValueError, InvalidOperation) as error:
                raise IncompleteMarketDataError(f"Некорректное поле {name}") from error

        fields: dict[str, object] = {
            "isin": row["isin"],
            "source": self.source,
            "currency": row["currency"],
            "nominal_per_bond": parse("nominal_per_bond", Decimal),
            "quote_kind": parse("quote_kind", QuoteKind),
            "quote_value": parse("quote_value", Decimal),
            "price_type": parse("price_type", PriceType),
            "quote_source": row["quote_source"],
            "quote_as_of_date": parse("quote_as_of_date", date.fromisoformat),
            "coupon_type": parse("coupon_type", CouponType),
            "fetched_at": fetched_at,
        }
        for name in ("accrued_per_bond", "modified_duration", "convexity"):
            fields[name] = parse(name, Decimal) if row[name] else None
        for name in ("accrued_as_of_date", "risk_as_of_date"):
            fields[name] = parse(name, date.fromisoformat) if row[name] else None
        fields["coupon_frequency"] = (
            parse("coupon_frequency", int) if row["coupon_frequency"] else None
        )
        for name in OPTIONAL_COLUMNS:
            fields[name] = row.get(name) or None
        return NormalizedBondData.from_provider(**fields)
