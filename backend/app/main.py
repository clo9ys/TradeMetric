from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.routes import auth, health
from app.config import get_settings
from app.db.engine import DatabaseManager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.db = DatabaseManager(get_settings().database_url)
    yield
    await app.state.db.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="TradeMetric", lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(auth.router)
    app.include_router(health.router)
    if get_settings().demo_mode:
        from app.api.routes import demo

        app.include_router(demo.router)
    return app


app = create_app()
