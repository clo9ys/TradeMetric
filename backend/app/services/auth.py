from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.db.models import AuthSession, User
from app.db.uow import UnitOfWork
from app.security import (
    DUMMY_PASSWORD_HASH,
    hash_session_token,
    new_csrf_token,
    new_session_token,
    verify_password,
)


class InvalidCredentials(Exception):
    pass


class NotAuthenticated(Exception):
    pass


@dataclass(frozen=True)
class LoginResult:
    token: str  # уйдёт в cookie
    csrf_token: str  # уйдёт в тело ответа
    user: User


class AuthService:
    def __init__(self, uow: UnitOfWork, session_ttl: timedelta) -> None:
        self._uow = uow
        self._session_ttl = session_ttl

    async def login(self, email: str, password: str) -> LoginResult:
        email = email.strip().lower()
        async with self._uow as uow:
            user = await uow.users.get_by_email(email)

            if user is None:
                verify_password(DUMMY_PASSWORD_HASH, password)
                raise InvalidCredentials

            if not verify_password(user.password_hash, password) or not user.is_active:
                raise InvalidCredentials

            token = new_session_token()
            auth_session = AuthSession(
                token_hash=hash_session_token(token),
                user_id=user.id,
                csrf_token=new_csrf_token(),
                expires_at=datetime.now(UTC) + self._session_ttl,
            )

            await uow.auth_sessions.add(auth_session)
            await uow.commit()

        return LoginResult(token=token, csrf_token=auth_session.csrf_token, user=user)

    async def authenticate(self, token: str) -> AuthSession:
        async with self._uow as uow:
            auth_session = await uow.auth_sessions.get_by_token_hash(hash_session_token(token))

            if (
                auth_session is None
                or auth_session.expires_at <= datetime.now(UTC)
                or not auth_session.user.is_active
            ):
                raise NotAuthenticated

        return auth_session

    async def logout(self, token: str) -> None:
        async with self._uow as uow:
            await uow.auth_sessions.delete(hash_session_token(token))
            await uow.commit()
