from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.errors import DomainError, FXRateUnavailableError, ProviderUnavailableError
from app.services.admin_users import AdminRuleViolation, EmailTaken, UserNotFound
from app.services.auth import InvalidCredentials, NotAuthenticated


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        code = 503 if isinstance(exc, (ProviderUnavailableError, FXRateUnavailableError)) else 400
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    @app.exception_handler(InvalidCredentials)
    async def invalid_credentials(request: Request, exc: InvalidCredentials) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Неверный email или пароль"},
        )

    @app.exception_handler(NotAuthenticated)
    async def not_authenticated(request: Request, exc: NotAuthenticated) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Требуется пройти авторизацию"},
        )

    @app.exception_handler(UserNotFound)
    async def user_not_found(request: Request, exc: UserNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Пользователь не найден"},
        )

    @app.exception_handler(EmailTaken)
    async def email_taken(request: Request, exc: EmailTaken) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Пользователь с таким email уже есть"},
        )

    @app.exception_handler(AdminRuleViolation)
    async def admin_rule_violation(request: Request, exc: AdminRuleViolation) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})
