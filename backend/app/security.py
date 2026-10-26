import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()  # Argon2id с параметрами по умолчанию из argon2-cffi


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True, если хеш сделан со старыми параметрами и его стоит пересчитать при входе."""
    return _hasher.check_needs_rehash(password_hash)


# Хеш, с которым сверяем пароль, когда пользователя с таким email нет.
# Так ответ на неверный email идёт столько же, сколько на неверный пароль.
DUMMY_PASSWORD_HASH = _hasher.hash(secrets.token_urlsafe(16))


def new_session_token() -> str:
    """Случайный токен для cookie. В базу кладём только hash_session_token() от него."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """SHA-256 в hex, ровно 64 символа: столбец auth_sessions.token_hash."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def tokens_equal(a: str, b: str) -> bool:
    """Сравнение за постоянное время, чтобы по скорости ответа нельзя было подобрать токен."""
    return hmac.compare_digest(a.encode(), b.encode())
