import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Calculation, CalculationTrade


class CalculationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, calculation: Calculation, trades: Sequence[CalculationTrade]) -> None:
        self._session.add(calculation)
        await self._session.flush()
        for trade in trades:
            trade.calculation_id = calculation.id
        self._session.add_all(trades)
        await self._session.flush()

    async def list_for_user(
        self, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Sequence[Calculation]:
        """Только сами расчёты, без сделок: для списка истории."""
        query = (
            select(Calculation)
            .where(Calculation.user_id == user_id)
            .order_by(Calculation.requested_at.desc(), Calculation.id)
            .limit(limit)
            .offset(offset)
        )
        return (await self._session.scalars(query)).all()

    async def get_for_user(
        self, calculation_id: uuid.UUID, user_id: uuid.UUID
    ) -> Calculation | None:
        """Расчёт со сделками и снимками. Чужой расчёт неотличим от несуществующего: None."""
        query = (
            select(Calculation)
            .where(Calculation.id == calculation_id, Calculation.user_id == user_id)
            .options(selectinload(Calculation.trades).selectinload(CalculationTrade.snapshot))
        )
        return await self._session.scalar(query)
