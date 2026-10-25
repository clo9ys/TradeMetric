from typing import Protocol

from app.domain.market_data import NormalizedBondData


class BondDataProvider(Protocol):
    async def get_bond(self, isin: str) -> NormalizedBondData: ...
