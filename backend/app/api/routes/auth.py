from typing import Annotated

from fastapi import APIRouter, Cookie, Response, status

from app.api.deps import SESSION_COOKIE, AuthServiceDep, CsrfSession, CurrentSession
from app.api.schemas.auth import AuthResponse, LoginRequest, UserOut
from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=get_settings().cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, response: Response, auth: AuthServiceDep) -> AuthResponse:
    result = await auth.login(email=body.email, password=body.password.get_secret_value())

    _set_session_cookie(response, result.token)
    return AuthResponse(user=UserOut.model_validate(result.user), csrf_token=result.csrf_token)


@router.get("/me", response_model=AuthResponse)
async def me(auth_session: CurrentSession) -> AuthResponse:
    return AuthResponse(
        user=UserOut.model_validate(auth_session.user),
        csrf_token=auth_session.csrf_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    _: CsrfSession,
    token: Annotated[str, Cookie(alias=SESSION_COOKIE)],
    response: Response,
    auth: AuthServiceDep,
) -> None:
    await auth.logout(token)

    _clear_session_cookie(response)
