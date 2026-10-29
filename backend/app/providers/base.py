from typing import Protocol

from app.domain.market_data import NormalizedBondData


class BondDataProvider(Protocol):
    """Общий контракт для адаптеров рыночных данных"""

    async def get_bond(self, isin: str) -> NormalizedBondData:
        """Возвращает полный нормализованный снимок по ISIN"""
        ...
