from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories import (
    AuthSessionRepository,
    CalculationRepository,
    SnapshotRepository,
    UserRepository,
)


class UnitOfWork:
    """Одна сессия и одна транзакция на одну операцию.

    async with uow:
        user = await uow.users.get_by_email(email)
        ...
        await uow.commit()

    Без явного commit() всё откатывается при выходе из блока, в том числе при исключении.

    session_factory нужен с expire_on_commit=False: иначе после commit() любое обращение
    к атрибутам модели полезет в базу, а в async это падает с MissingGreenlet.
    """

    users: UserRepository
    auth_sessions: AuthSessionRepository
    snapshots: SnapshotRepository
    calculations: CalculationRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError("UnitOfWork уже открыт, вложенно его не используем")
        self._session = self._session_factory()
        self.users = UserRepository(self._session)
        self.auth_sessions = AuthSessionRepository(self._session)
        self.snapshots = SnapshotRepository(self._session)
        self.calculations = CalculationRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._session is not None
        try:
            if exc_type is not None:
                await self._session.rollback()
        finally:
            # close() тоже откатывает незакоммиченное, но, в отличие от rollback(),
            # не сбрасывает загруженные объекты: их можно читать после выхода из блока

            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        assert self._session is not None, "commit() вне async with"
        await self._session.commit()
