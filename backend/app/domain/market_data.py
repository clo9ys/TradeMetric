import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Self

from app.domain.enums import CouponType, MarketDataSource, PriceType, QuoteKind
from app.domain.errors import IncompleteMarketDataError, InvalidISINError, StaleMarketDataError
from app.domain.isin import validate_isin

CURRENCY_PATTERN = re.compile(r"[A-Z]{3}\Z")


@dataclass(frozen=True, kw_only=True, slots=True)
class NormalizedBondData:
    """Снимок одной облигации с денежными величинами в валюте бумаги на одну штуку"""

    isin: str
    source: MarketDataSource
    currency: str
    nominal_per_bond: Decimal
    quote_kind: QuoteKind
    quote_value: Decimal
    price_type: PriceType
    quote_source: str
    quote_as_of_date: date
    coupon_type: CouponType
    fetched_at: datetime
    accrued_per_bond: Decimal | None = None
    accrued_as_of_date: date | None = None
    coupon_frequency: int | None = None
    modified_duration: Decimal | None = None
    convexity: Decimal | None = None
    risk_as_of_date: date | None = None
    provider_instrument_id: str | None = None
    issue_name: str | None = None
    issuer_name: str | None = None
    quote_as_of_at: datetime | None = None
    risk_as_of_at: datetime | None = None

    @classmethod
    def from_provider(cls, **fields: object) -> Self:
        """Создаёт снимок из данных поставщика, сообщая о неполном ответе понятной ошибкой"""
        try:
            # при создании автоматически вызывается __post_init__
            return cls(**fields)
        except (TypeError, InvalidISINError) as error:
            raise IncompleteMarketDataError("Некорректный или неполный ответ поставщика") from error

    def __post_init__(self) -> None:
        """Проверяет и нормализует поля сразу после создания объекта"""
        try:
            normalized_isin = validate_isin(self.isin)
        except InvalidISINError as error:
            raise IncompleteMarketDataError("Поставщик вернул некорректный ISIN") from error
        object.__setattr__(self, "isin", normalized_isin)

        if not isinstance(self.source, MarketDataSource):
            raise IncompleteMarketDataError("Неизвестный источник рыночных данных")
        if not isinstance(self.currency, str) or not CURRENCY_PATTERN.fullmatch(self.currency):
            raise IncompleteMarketDataError("Валюта должна быть трёхбуквенным кодом ISO 4217")
        if not isinstance(self.quote_kind, QuoteKind):
            raise IncompleteMarketDataError("Неизвестная единица котировки")
        if not isinstance(self.price_type, PriceType):
            raise IncompleteMarketDataError("Неизвестный тип цены")
        if not isinstance(self.coupon_type, CouponType):
            raise IncompleteMarketDataError("Неизвестный тип купона")
        if not isinstance(self.quote_source, str) or not self.quote_source.strip():
            raise IncompleteMarketDataError("Не указан источник котировки")

        self._require_date("quote_as_of_date", self.quote_as_of_date)
        self._require_aware_datetime("fetched_at", self.fetched_at)
        for name in ("accrued_as_of_date", "risk_as_of_date"):
            value = getattr(self, name)
            if value is not None:
                self._require_date(name, value)
        for name in ("quote_as_of_at", "risk_as_of_at"):
            value = getattr(self, name)
            if value is not None:
                self._require_aware_datetime(name, value)

        for name in ("nominal_per_bond", "quote_value"):
            self._require_decimal(name, getattr(self, name), positive=True)
        for name in ("accrued_per_bond", "modified_duration", "convexity"):
            value = getattr(self, name)
            if value is not None:
                self._require_decimal(name, value)
        if self.accrued_per_bond is not None and self.accrued_per_bond < 0:
            raise IncompleteMarketDataError("НКД не может быть отрицательным")
        if self.modified_duration is not None and self.modified_duration < 0:
            raise IncompleteMarketDataError("Модифицированная дюрация не может быть отрицательной")

        if self.coupon_frequency is not None and (
            type(self.coupon_frequency) is not int or not 1 <= self.coupon_frequency <= 32767
        ):
            raise IncompleteMarketDataError("Частота купонов должна быть положительной")
        if self.price_type is PriceType.CLEAN and (
            self.accrued_per_bond is None or self.accrued_as_of_date is None
        ):
            raise IncompleteMarketDataError("Для чистой цены необходимы НКД и его дата")
        if (self.accrued_per_bond is None) != (self.accrued_as_of_date is None):
            raise IncompleteMarketDataError("НКД и его дата должны быть указаны вместе")
        if self.coupon_type is CouponType.FIXED and (
            self.modified_duration is None
            or self.convexity is None
            or self.risk_as_of_date is None
        ):
            raise IncompleteMarketDataError("Для фиксированного купона необходимы риск-параметры")
        if self.coupon_type is CouponType.FLOATING and self.coupon_frequency is None:
            raise IncompleteMarketDataError("Для плавающего купона нужна частота выплат")
        if self.risk_as_of_at is not None and self.risk_as_of_date is None:
            raise IncompleteMarketDataError("Время риск-параметров требует даты")

    def validate_freshness(self, *, calculation_date: date, last_trading_date: date) -> None:
        """Проверка свежести данных"""
        self._require_date("calculation_date", calculation_date)
        self._require_date("last_trading_date", last_trading_date)
        if last_trading_date > calculation_date:
            raise ValueError("Последний торговый день не может быть позже даты расчёта")
        if self.quote_as_of_date != last_trading_date:
            raise StaleMarketDataError("Котировка не относится к последнему торговому дню")
        if (self.coupon_type is CouponType.FIXED and self.risk_as_of_date != last_trading_date):
            raise StaleMarketDataError("Риск-параметры не относятся к последнему торговому дню")
        if self.accrued_as_of_date is not None and self.accrued_as_of_date > calculation_date:
            raise StaleMarketDataError("Дата НКД позже даты расчёта")

    @staticmethod
    def _require_decimal(name: str, value: object, *, positive: bool = False) -> None:
        if not isinstance(value, Decimal) or not value.is_finite():
            raise IncompleteMarketDataError(f"{name} должен быть конечным Decimal")
        if positive and value <= 0:
            raise IncompleteMarketDataError(f"{name} должен быть больше нуля")

    @staticmethod
    def _require_date(name: str, value: object) -> None:
        if type(value) is not date:
            raise IncompleteMarketDataError(f"{name} должен быть датой")

    @staticmethod
    def _require_aware_datetime(name: str, value: object) -> None:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise IncompleteMarketDataError(f"{name} должен содержать часовой пояс")
