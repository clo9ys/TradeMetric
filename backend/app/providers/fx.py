from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FXRate:
    rub_per_unit: Decimal
    effective_date: date
    source: str


class FXRateProvider(Protocol):
    async def get_rate(self, currency: str, calculation_date: date) -> FXRate: ...
