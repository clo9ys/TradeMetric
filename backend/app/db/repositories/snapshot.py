from collections.abc import Sequence
from datetime import date

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InstrumentSnapshot


class SnapshotRepository:
    """Неизменяемые снимки могут повторно использоваться расчётами одного дня"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_fetched_on_date(self, isins: Sequence[str], calculation_date: date) -> list[InstrumentSnapshot]:
        if not isins:
            return []
        statement = (
            select(InstrumentSnapshot)
            .where(
                InstrumentSnapshot.isin.in_(isins),
                cast(func.timezone("Europe/Moscow", InstrumentSnapshot.fetched_at), Date)
                == calculation_date,
            )
            .order_by(InstrumentSnapshot.fetched_at.desc())
        )
        result = await self._session.scalars(statement)
        return list(result)

    async def add_many(self, snapshots: Sequence[InstrumentSnapshot]) -> None:
        self._session.add_all(snapshots)
        await self._session.flush()
