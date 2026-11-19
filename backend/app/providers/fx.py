from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from app.domain.errors import FXRateUnavailableError
from app.domain.market_data import CURRENCY_PATTERN


@dataclass(frozen=True, slots=True)
class FXRate:
    """Курс за одну единицу валюты в рублях с датой его действия"""

    rub_per_unit: Decimal
    effective_date: date
    source: str
    currency: str
    fetched_at: datetime

    def validate_for(self, currency: str, calculation_date: date) -> None:
        """Не позволяет сохранить курс другой валюты, будущий или неполный курс."""
        if (
            self.currency != currency
            or not CURRENCY_PATTERN.fullmatch(currency)
            or not isinstance(self.rub_per_unit, Decimal)
            or not self.rub_per_unit.is_finite()
            or self.rub_per_unit <= 0
            or type(self.effective_date) is not date
            or self.effective_date > calculation_date
            or not isinstance(self.source, str)
            or not self.source.strip()
            or len(self.source) > 50
            or not isinstance(self.fetched_at, datetime)
            or self.fetched_at.tzinfo is None
            or self.fetched_at.utcoffset() is None
        ):
            raise FXRateUnavailableError(f"Нет действующего курса {currency} на дату расчёта")


class FXRateProvider(Protocol):
    """Контракт получения курса, действующего на дату расчёта"""

    async def get_rate(self, currency: str, calculation_date: date) -> FXRate:
        """Возвращает курс валюты к рублю на дату расчёта"""
        ...
