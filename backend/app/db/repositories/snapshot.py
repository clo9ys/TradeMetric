from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InstrumentSnapshot


class SnapshotRepository:
    """Снимки только вставляются: для каждого расчёта свои, старые не трогаем."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, snapshots: Sequence[InstrumentSnapshot]) -> None:
        # после flush у снимков есть id и посчитанная базой dirty_price_per_bond
        self._session.add_all(snapshots)
        await self._session.flush()
