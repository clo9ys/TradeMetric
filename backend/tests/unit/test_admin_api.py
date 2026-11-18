import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from app.config import get_settings
from app.db.models import User
from app.domain.enums import UserRole
from app.services.admin_users import AdminRuleViolation, EmailTaken, UserNotFound

CSRF = "csrf-token-123"
ADMIN_ID = uuid.uuid4()


def make_user(email: str = "employee@example.com", role: str = "user") -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash="secret-hash",
        role=role,
        is_active=True,
        created_at=datetime(2026, 11, 16, tzinfo=UTC),
    )


class FakeAdminService:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.calls: list[tuple] = []

    def _maybe_fail(self):
        if self.error is not None:
            raise self.error

    async def list_users(self):
        return [make_user("admin@example.com", "admin"), make_user()]

    async def create_user(self, email, password, role):
        self._maybe_fail()
        self.calls.append(("create", email, password, role))
        return make_user(email, role.value)

    async def update_user(self, actor_id, user_id, *, role=None, is_active=None):
        self._maybe_fail()
        self.calls.append(("update", actor_id, user_id, role, is_active))
        return make_user()

    async def change_password(self, user_id, password):
        self._maybe_fail()
        self.calls.append(("password", user_id, password))

    async def delete_user(self, actor_id, user_id):
        self._maybe_fail()
        self.calls.append(("delete", actor_id, user_id))


@pytest.fixture
def service():
    return FakeAdminService()


@pytest.fixture
def make_client(monkeypatch, service):
    for name, value in {
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "test",
        "POSTGRES_DB": "test",
        "DEMO_MODE": "false",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()

    from app.api.deps import get_admin_user_service, get_current_session
    from app.main import create_app

    def build(role: str) -> httpx.AsyncClient:
        app = create_app()
        session = SimpleNamespace(user=SimpleNamespace(id=ADMIN_ID, role=role), csrf_token=CSRF)
        app.dependency_overrides[get_current_session] = lambda: session
        app.dependency_overrides[get_admin_user_service] = lambda: service
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    yield build
    get_settings.cache_clear()


async def test_regular_user_gets_403(make_client):
    async with make_client("user") as client:
        response = await client.get("/api/admin/users")

    assert response.status_code == 403
    assert response.json() == {"detail": "Нужны права администратора"}


async def test_admin_lists_users_without_password_hashes(make_client):
    async with make_client("admin") as client:
        response = await client.get("/api/admin/users")

    assert response.status_code == 200
    first = response.json()[0]
    assert set(first) == {"id", "email", "role", "is_active", "created_at"}
    assert first["role"] == "admin"


async def test_create_without_csrf_is_forbidden(make_client, service):
    async with make_client("admin") as client:
        response = await client.post(
            "/api/admin/users", json={"email": "new@example.com", "password": "secret-pass"}
        )

    assert response.status_code == 403
    assert service.calls == []


async def test_admin_creates_user(make_client, service):
    async with make_client("admin") as client:
        response = await client.post(
            "/api/admin/users",
            json={"email": "new@example.com", "password": "secret-pass"},
            headers={"X-CSRF-Token": CSRF},
        )

    assert response.status_code == 201
    assert response.json()["email"] == "new@example.com"
    assert service.calls == [("create", "new@example.com", "secret-pass", UserRole.USER)]


async def test_short_password_is_rejected(make_client, service):
    async with make_client("admin") as client:
        response = await client.post(
            "/api/admin/users",
            json={"email": "new@example.com", "password": "short"},
            headers={"X-CSRF-Token": CSRF},
        )

    assert response.status_code == 422
    assert service.calls == []


async def test_taken_email_is_409(make_client, service):
    service.error = EmailTaken()
    async with make_client("admin") as client:
        response = await client.post(
            "/api/admin/users",
            json={"email": "taken@example.com", "password": "secret-pass"},
            headers={"X-CSRF-Token": CSRF},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "Пользователь с таким email уже есть"}


async def test_update_passes_actor_and_returns_user(make_client, service):
    target = uuid.uuid4()
    async with make_client("admin") as client:
        response = await client.patch(
            f"/api/admin/users/{target}",
            json={"is_active": False},
            headers={"X-CSRF-Token": CSRF},
        )

    assert response.status_code == 200
    assert service.calls == [("update", ADMIN_ID, target, None, False)]


async def test_empty_update_is_rejected(make_client, service):
    async with make_client("admin") as client:
        response = await client.patch(
            f"/api/admin/users/{uuid.uuid4()}", json={}, headers={"X-CSRF-Token": CSRF}
        )

    assert response.status_code == 422
    assert service.calls == []


async def test_rule_violation_is_409_with_its_text(make_client, service):
    service.error = AdminRuleViolation("Нельзя удалить себя")
    async with make_client("admin") as client:
        response = await client.delete(
            f"/api/admin/users/{ADMIN_ID}", headers={"X-CSRF-Token": CSRF}
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "Нельзя удалить себя"}


async def test_unknown_user_is_404(make_client, service):
    service.error = UserNotFound()
    async with make_client("admin") as client:
        response = await client.put(
            f"/api/admin/users/{uuid.uuid4()}/password",
            json={"password": "brand-new-pass"},
            headers={"X-CSRF-Token": CSRF},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Пользователь не найден"}


async def test_password_change_and_delete_return_204(make_client, service):
    target = uuid.uuid4()
    async with make_client("admin") as client:
        changed = await client.put(
            f"/api/admin/users/{target}/password",
            json={"password": "brand-new-pass"},
            headers={"X-CSRF-Token": CSRF},
        )
        deleted = await client.delete(f"/api/admin/users/{target}", headers={"X-CSRF-Token": CSRF})

    assert (changed.status_code, deleted.status_code) == (204, 204)
    assert service.calls == [
        ("password", target, "brand-new-pass"),
        ("delete", ADMIN_ID, target),
    ]
