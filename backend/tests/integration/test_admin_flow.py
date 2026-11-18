import os
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.uow import UnitOfWork
from app.domain.enums import UserRole
from app.services.admin_users import AdminUserService

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin-password"


@pytest.fixture
async def client(monkeypatch):
    """Приложение целиком на настоящей базе: своя схема, миграции, вход через cookie"""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    for name, value in {"POSTGRES_USER": "x", "POSTGRES_PASSWORD": "x", "POSTGRES_DB": "x"}.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()

    schema = f"admin_flow_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(url)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        async with engine.begin() as connection:
            config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
            config.attributes["connection"] = connection.sync_connection
            await connection.run_sync(lambda _: command.upgrade(config, "head"))

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        await AdminUserService(UnitOfWork(session_factory)).create_user(
            ADMIN_EMAIL, ADMIN_PASSWORD, UserRole.ADMIN
        )

        from app.main import create_app

        app = create_app()
        app.state.db = SimpleNamespace(session_factory=session_factory)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            yield http
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        await admin_engine.dispose()
        get_settings.cache_clear()


async def login(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    return await client.post("/api/auth/login", json={"email": email, "password": password})


async def test_admin_manages_users_through_the_real_stack(client):
    logged_in = await login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["role"] == "admin"
    csrf = {"X-CSRF-Token": logged_in.json()["csrf_token"]}
    admin_id = logged_in.json()["user"]["id"]

    created = await client.post(
        "/api/admin/users",
        json={"email": " Employee@Example.com ", "password": "employee-pass"},
        headers=csrf,
    )
    assert created.status_code == 201
    employee = created.json()
    assert (employee["email"], employee["role"]) == ("employee@example.com", "user")

    duplicate = await client.post(
        "/api/admin/users",
        json={"email": "employee@example.com", "password": "employee-pass"},
        headers=csrf,
    )
    assert duplicate.status_code == 409

    blocked = await client.patch(
        f"/api/admin/users/{employee['id']}", json={"is_active": False}, headers=csrf
    )
    assert blocked.status_code == 200
    assert blocked.json()["is_active"] is False

    deleting_self = await client.delete(f"/api/admin/users/{admin_id}", headers=csrf)
    assert deleting_self.status_code == 409

    listed = await client.get("/api/admin/users")
    assert sorted(user["email"] for user in listed.json()) == [ADMIN_EMAIL, "employee@example.com"]

    deleted = await client.delete(f"/api/admin/users/{employee['id']}", headers=csrf)
    assert deleted.status_code == 204

    own_password = await client.put(
        f"/api/admin/users/{admin_id}/password", json={"password": "new-admin-pass"}, headers=csrf
    )
    assert own_password.status_code == 204
    assert (await client.get("/api/admin/users")).status_code == 401
    assert (await login(client, ADMIN_EMAIL, "new-admin-pass")).status_code == 200


async def test_blocked_user_loses_open_session(client):
    admin = await login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    created = await client.post(
        "/api/admin/users",
        json={"email": "worker@example.com", "password": "worker-pass"},
        headers={"X-CSRF-Token": admin.json()["csrf_token"]},
    )

    assert (await login(client, "worker@example.com", "worker-pass")).status_code == 200
    worker_cookie = client.cookies.get("tm_session")

    relogged = await login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    blocked = await client.patch(
        f"/api/admin/users/{created.json()['id']}",
        json={"is_active": False},
        headers={"X-CSRF-Token": relogged.json()["csrf_token"]},
    )
    assert blocked.status_code == 200

    client.cookies.clear()
    client.cookies.set("tm_session", worker_cookie)
    assert (await client.get("/api/auth/me")).status_code == 401
