from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models import AuthSession


class AuthSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_token_hash(self, token_hash: str) -> AuthSession | None:
        """Сессия вместе с пользователем: AuthService проверяет и срок, и is_active."""
        query = (
            select(AuthSession)
            .where(AuthSession.token_hash == token_hash)
            .options(joinedload(AuthSession.user))
        )
        return await self._session.scalar(query)

    async def add(self, auth_session: AuthSession) -> None:
        self._session.add(auth_session)
        await self._session.flush()

    async def delete(self, token_hash: str) -> None:
        await self._session.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash))
