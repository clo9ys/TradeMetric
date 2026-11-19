from datetime import timedelta
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status

from app.config import get_settings
from app.db.models import AuthSession
from app.db.uow import UnitOfWork
from app.domain.enums import UserRole
from app.providers.cbr import CBRRateAdapter
from app.providers.factory import build_bond_provider
from app.security import tokens_equal
from app.services.admin_users import AdminUserService
from app.services.auth import AuthService, NotAuthenticated
from app.services.calculation import CalculationService
from app.services.market_data import MarketDataService

SESSION_COOKIE = "tm_session"
CSRF_HEADER = "X-CSRF-Token"


def get_uow(request: Request) -> UnitOfWork:
    # DatabaseManager будет лежать в app.state.db, его создаст lifespan в main.py
    return UnitOfWork(request.app.state.db.session_factory)


def get_auth_service(uow: Annotated[UnitOfWork, Depends(get_uow)]) -> AuthService:
    return AuthService(uow, timedelta(hours=get_settings().session_ttl_hours))


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_session(
    auth: AuthServiceDep,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> AuthSession:
    if token is None:
        raise NotAuthenticated
    return await auth.authenticate(token)


CurrentSession = Annotated[AuthSession, Depends(get_current_session)]


async def require_csrf(
    auth_session: CurrentSession,
    csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> AuthSession:
    if csrf_token is None or not tokens_equal(csrf_token, auth_session.csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="CSRF токен отсутствует или неверный")

    return auth_session


CsrfSession = Annotated[AuthSession, Depends(require_csrf)]


async def require_admin(auth_session: CurrentSession) -> AuthSession:
    """Пускает только админов. Остальным 403 с текстом «Нужны права администратора»"""
    if auth_session.user.role != UserRole.ADMIN.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Нужны права администратора")
    return auth_session


AdminSession = Annotated[AuthSession, Depends(require_admin)]


def get_admin_user_service(uow: Annotated[UnitOfWork, Depends(get_uow)]) -> AdminUserService:
    return AdminUserService(uow)


AdminUserServiceDep = Annotated[AdminUserService, Depends(get_admin_user_service)]


def get_market_data_service(request: Request) -> MarketDataService:
    settings = get_settings()
    provider, source = build_bond_provider(settings)
    factory = request.app.state.db.session_factory
    return MarketDataService(UnitOfWork(factory), provider, source=source)


def get_calculation_service(request: Request) -> CalculationService:
    settings = get_settings()
    factory = request.app.state.db.session_factory
    market_data = get_market_data_service(request)
    return CalculationService(
        UnitOfWork(factory), market_data, CBRRateAdapter.from_settings(settings)
    )


CalculationServiceDep = Annotated[CalculationService, Depends(get_calculation_service)]
