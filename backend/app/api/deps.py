from datetime import timedelta
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status

from app.config import get_settings
from app.db.models import AuthSession
from app.db.uow import UnitOfWork
from app.security import tokens_equal
from app.services.auth import AuthService, NotAuthenticated

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
