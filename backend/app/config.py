from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

# Один .env в корне репо: его читают и docker compose, и приложение при локальном запуске.
# В контейнере файла нет, переменные приходят из окружения.
ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_ENV_FILE, extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str
    postgres_password: str
    postgres_db: str

    session_ttl_hours: int = 12
    cookie_secure: bool = False  # на проде в .env будет COOKIE_SECURE=true

    @property
    def database_url(self) -> URL:
        # URL.create сам экранирует спецсимволы в пароле
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
