import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.fixture
async def db_session():
    """Сессия на чистой схеме с накатанными миграциями. Всё удаляется после теста"""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")

    engine = create_async_engine(url)
    schema = f"admin_test_{uuid.uuid4().hex}"
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {schema}"))
            await connection.execute(text(f"SET search_path TO {schema}"))
            config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
            config.attributes["connection"] = connection.sync_connection
            await connection.run_sync(lambda _: command.upgrade(config, "head"))
            async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                yield session
            await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    finally:
        await engine.dispose()
