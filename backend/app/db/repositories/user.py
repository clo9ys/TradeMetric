import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.domain.enums import UserRole


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        return await self._session.scalar(select(User).where(User.email == email))

    async def add(self, user: User) -> None:
        self._session.add(user)
        await self._session.flush()

    async def list_all(self) -> list[User]:
        query = select(User).order_by(User.created_at, User.email)
        return list(await self._session.scalars(query))

    async def delete(self, user: User) -> None:
        await self._session.delete(user)
        await self._session.flush()

    async def count_active_admins(self) -> int:
        """Сколько активных админов. Строки блокируются до конца транзакции: если два админа
        одновременно снимают роль друг с друга, второй дождётся первого и увидит новое число.
        Postgres не даёт совместить FOR UPDATE с count(), поэтому считаем в Python"""
        query = (
            select(User.id)
            .where(User.role == UserRole.ADMIN.value, User.is_active.is_(True))
            .with_for_update()
        )
        return len((await self._session.scalars(query)).all())
