from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.fx_rate_snapshot import FXRateSnapshot


class FXRateSnapshotRepository:
    """Сохраняет курсы внутри общей транзакции расчёта."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, snapshots: Sequence[FXRateSnapshot]) -> None:
        self._session.add_all(snapshots)
        await self._session.flush()
