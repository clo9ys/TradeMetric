import uuid

from sqlalchemy.exc import IntegrityError

from app.db.models import User
from app.db.uow import UnitOfWork
from app.domain.enums import UserRole
from app.security import hash_password


class UserNotFound(Exception):
    pass


class EmailTaken(Exception):
    pass


class AdminRuleViolation(Exception):
    """Действие нарушает правило админки. Текст исключения уходит админу в ответе"""


class AdminUserService:
    """Управление аккаунтами. Правила проверяются в той же транзакции, что и изменение"""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def list_users(self) -> list[User]:
        async with self._uow as uow:
            return await uow.users.list_all()

    async def create_user(self, email: str, password: str, role: UserRole) -> User:
        email = email.strip().lower()
        async with self._uow as uow:
            if await uow.users.get_by_email(email) is not None:
                raise EmailTaken
            user = User(email=email, password_hash=hash_password(password), role=role.value)
            try:
                await uow.users.add(user)
                await uow.commit()
            except IntegrityError as exc:  # такой же email успели создать параллельно
                raise EmailTaken from exc
        return user

    async def update_user(
        self,
        actor_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> User:
        async with self._uow as uow:
            user = await self._get(uow, user_id)
            active_admins = await uow.users.count_active_admins()
            self._check_can_update(
                actor_id, user, role=role, is_active=is_active, active_admins=active_admins
            )
            if role is not None:
                user.role = role.value
            if is_active is not None:
                user.is_active = is_active
            await uow.auth_sessions.delete_for_user(user.id)
            await uow.commit()
        return user

    async def change_password(self, user_id: uuid.UUID, password: str) -> None:
        async with self._uow as uow:
            user = await self._get(uow, user_id)
            user.password_hash = hash_password(password)
            await uow.auth_sessions.delete_for_user(user.id)
            await uow.commit()

    async def delete_user(self, actor_id: uuid.UUID, user_id: uuid.UUID) -> None:
        async with self._uow as uow:
            user = await self._get(uow, user_id)
            active_admins = await uow.users.count_active_admins()
            has_calculations = await uow.calculations.exists_for_user(user.id)
            self._check_can_delete(
                actor_id, user, active_admins=active_admins, has_calculations=has_calculations
            )
            await uow.users.delete(user)
            await uow.commit()

    @staticmethod
    async def _get(uow: UnitOfWork, user_id: uuid.UUID) -> User:
        user = await uow.users.get_by_id(user_id)
        if user is None:
            raise UserNotFound
        return user

    @staticmethod
    def _check_can_update(
        actor_id: uuid.UUID,
        user: User,
        *,
        role: UserRole | None,
        is_active: bool | None,
        active_admins: int,
    ) -> None:
        """Можно ли поменять пользователю роль или статус. Нарушение -> AdminRuleViolation

        - свою роль менять и себя блокировать нельзя
        - нельзя снять роль или заблокировать последнего активного админа.
          active_admins уже посчитан с блокировкой строк, см. count_active_admins
        """
        # TODO(Максим): правила, 5–8 строк. Тексты ошибок смотри в tests/unit/test_admin_users.py

    @staticmethod
    def _check_can_delete(
        actor_id: uuid.UUID,
        user: User,
        *,
        active_admins: int,
        has_calculations: bool,
    ) -> None:
        """Можно ли удалить пользователя. Нарушение -> AdminRuleViolation

        - себя удалить нельзя
        - последнего активного админа удалить нельзя
        - пользователя с историей расчётов удалить нельзя: история неизменна,
          такого пользователя блокируют
        """
        # TODO(Максим): правила, 5–8 строк. Тексты ошибок смотри в tests/unit/test_admin_users.py
