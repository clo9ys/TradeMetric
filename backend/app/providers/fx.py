from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FXRate:
    """Курс за одну единицу валюты в рублях с датой его действия"""

    rub_per_unit: Decimal
    effective_date: date
    source: str


class FXRateProvider(Protocol):
    """Контракт получения курса, действующего на дату расчёта"""

    async def get_rate(self, currency: str, calculation_date: date) -> FXRate:
        """Возвращает курс валюты к рублю на дату расчёта"""
        ...
