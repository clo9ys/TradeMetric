import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import User
from app.domain.enums import UserRole
from app.security import hash_password, verify_password
from app.services.admin_users import (
    AdminRuleViolation,
    AdminUserService,
    EmailTaken,
    UserNotFound,
)


class FakeUsers:
    def __init__(self, users: list[User]) -> None:
        self.items = {user.id: user for user in users}
        self.active_admins: int | None = None  # подменяет подсчёт, чтобы смоделировать гонку
        self.fail_on_add = False

    async def get_by_id(self, user_id):
        return self.items.get(user_id)

    async def get_by_email(self, email):
        return next((user for user in self.items.values() if user.email == email), None)

    async def add(self, user):
        if self.fail_on_add:
            raise IntegrityError("INSERT INTO users", {}, Exception("duplicate key"))
        user.id = user.id or uuid.uuid4()
        self.items[user.id] = user

    async def list_all(self):
        return list(self.items.values())

    async def delete(self, user):
        del self.items[user.id]

    async def count_active_admins(self):
        if self.active_admins is not None:
            return self.active_admins
        return sum(1 for user in self.items.values() if user.role == "admin" and user.is_active)


class FakeAuthSessions:
    def __init__(self) -> None:
        self.revoked: list[uuid.UUID] = []

    async def delete_for_user(self, user_id):
        self.revoked.append(user_id)


class FakeCalculations:
    def __init__(self, owners) -> None:
        self.owners = set(owners)

    async def exists_for_user(self, user_id):
        return user_id in self.owners


class FakeUnitOfWork:
    def __init__(self, users: list[User], calculation_owners=()) -> None:
        self.users = FakeUsers(users)
        self.auth_sessions = FakeAuthSessions()
        self.calculations = FakeCalculations(calculation_owners)
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return None

    async def commit(self):
        self.commits += 1


def make_user(email: str, role: str = "user", *, is_active: bool = True) -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("old-password"),
        role=role,
        is_active=is_active,
    )


@pytest.fixture
def admin():
    return make_user("admin@example.com", "admin")


@pytest.fixture
def second_admin():
    return make_user("second@example.com", "admin")


@pytest.fixture
def employee():
    return make_user("employee@example.com")


def service_for(*users: User, calculation_owners=()) -> tuple[AdminUserService, FakeUnitOfWork]:
    uow = FakeUnitOfWork(list(users), calculation_owners)
    return AdminUserService(uow), uow  # type: ignore[arg-type]


# --- создание ---


async def test_create_user_normalizes_email_and_hashes_password(admin):
    service, uow = service_for(admin)

    user = await service.create_user("  New.User@Example.COM ", "secret-pass", UserRole.USER)

    assert user.email == "new.user@example.com"
    assert user.role == "user"
    assert verify_password(user.password_hash, "secret-pass")
    assert uow.commits == 1


async def test_create_user_rejects_same_email_in_other_case(admin, employee):
    service, uow = service_for(admin, employee)

    with pytest.raises(EmailTaken):
        await service.create_user("Employee@Example.com", "secret-pass", UserRole.USER)
    assert uow.commits == 0


async def test_create_user_reports_concurrent_duplicate_as_email_taken(admin):
    service, uow = service_for(admin)
    uow.users.fail_on_add = True

    with pytest.raises(EmailTaken):
        await service.create_user("race@example.com", "secret-pass", UserRole.USER)


# --- изменение ---


async def test_admin_can_promote_user_and_sessions_are_revoked(admin, employee):
    service, uow = service_for(admin, employee)

    user = await service.update_user(admin.id, employee.id, role=UserRole.ADMIN)

    assert user.role == "admin"
    assert uow.auth_sessions.revoked == [employee.id]
    assert uow.commits == 1


async def test_blocking_user_revokes_sessions(admin, employee):
    service, uow = service_for(admin, employee)

    user = await service.update_user(admin.id, employee.id, is_active=False)

    assert user.is_active is False
    assert uow.auth_sessions.revoked == [employee.id]


async def test_change_own_password_revokes_own_sessions(admin):
    service, uow = service_for(admin)

    await service.change_password(admin.id, "brand-new-pass")

    assert verify_password(admin.password_hash, "brand-new-pass")
    assert not verify_password(admin.password_hash, "old-password")
    assert uow.auth_sessions.revoked == [admin.id]


async def test_delete_user_without_calculations(admin, employee):
    service, uow = service_for(admin, employee)

    await service.delete_user(admin.id, employee.id)

    assert employee.id not in uow.users.items
    assert uow.commits == 1


async def test_unknown_user_is_not_found(admin):
    service, _ = service_for(admin)
    missing = uuid.uuid4()

    with pytest.raises(UserNotFound):
        await service.update_user(admin.id, missing, is_active=False)
    with pytest.raises(UserNotFound):
        await service.change_password(missing, "brand-new-pass")
    with pytest.raises(UserNotFound):
        await service.delete_user(admin.id, missing)


# --- правила (их пишет Максим в _check_can_update и _check_can_delete) ---


async def test_admin_cannot_change_own_role(admin, second_admin):
    service, uow = service_for(admin, second_admin)

    with pytest.raises(AdminRuleViolation, match="Нельзя менять свою роль или блокировать себя"):
        await service.update_user(admin.id, admin.id, role=UserRole.USER)
    assert admin.role == "admin"
    assert uow.commits == 0


async def test_admin_cannot_block_self(admin, second_admin):
    service, _ = service_for(admin, second_admin)

    with pytest.raises(AdminRuleViolation, match="Нельзя менять свою роль или блокировать себя"):
        await service.update_user(admin.id, admin.id, is_active=False)
    assert admin.is_active is True


async def test_cannot_demote_last_active_admin(admin, second_admin):
    # второй админ в ту же секунду снял роль с первого: после блокировки строк админ один
    service, uow = service_for(admin, second_admin)
    uow.users.active_admins = 1

    with pytest.raises(AdminRuleViolation, match="Нельзя оставить систему без администратора"):
        await service.update_user(admin.id, second_admin.id, role=UserRole.USER)
    assert second_admin.role == "admin"


async def test_cannot_block_last_active_admin(admin, second_admin):
    service, uow = service_for(admin, second_admin)
    uow.users.active_admins = 1

    with pytest.raises(AdminRuleViolation, match="Нельзя оставить систему без администратора"):
        await service.update_user(admin.id, second_admin.id, is_active=False)
    assert second_admin.is_active is True


async def test_last_admin_rule_ignores_regular_users(admin, employee):
    service, _ = service_for(admin, employee)

    await service.update_user(admin.id, employee.id, is_active=False)
    await service.update_user(admin.id, employee.id, role=UserRole.ADMIN)

    assert employee.role == "admin"


async def test_admin_cannot_delete_self(admin, second_admin):
    service, uow = service_for(admin, second_admin)

    with pytest.raises(AdminRuleViolation, match="Нельзя удалить себя"):
        await service.delete_user(admin.id, admin.id)
    assert admin.id in uow.users.items


async def test_cannot_delete_last_active_admin(admin, second_admin):
    service, uow = service_for(admin, second_admin)
    uow.users.active_admins = 1

    with pytest.raises(AdminRuleViolation, match="Нельзя оставить систему без администратора"):
        await service.delete_user(admin.id, second_admin.id)
    assert second_admin.id in uow.users.items


async def test_cannot_delete_user_with_calculations(admin, employee):
    service, uow = service_for(admin, employee, calculation_owners=[employee.id])

    with pytest.raises(AdminRuleViolation, match="заблокируйте его вместо удаления"):
        await service.delete_user(admin.id, employee.id)
    assert employee.id in uow.users.items
    assert uow.commits == 0
