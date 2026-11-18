from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.models import AuthSession, Calculation, User
from app.db.repositories import AuthSessionRepository, CalculationRepository, UserRepository


def make_user(email: str, *, role: str = "user", is_active: bool = True) -> User:
    return User(email=email, password_hash="x", role=role, is_active=is_active)


def make_session(user: User, token: str) -> AuthSession:
    return AuthSession(
        token_hash=token * 64,
        user_id=user.id,
        csrf_token="csrf",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


async def test_count_active_admins_ignores_blocked_and_users(db_session):
    db_session.add_all(
        [
            make_user("a1@example.com", role="admin"),
            make_user("a2@example.com", role="admin"),
            make_user("a3@example.com", role="admin", is_active=False),
            make_user("u1@example.com"),
        ]
    )
    await db_session.flush()

    assert await UserRepository(db_session).count_active_admins() == 2


async def test_list_all_returns_every_user(db_session):
    db_session.add_all([make_user("b@example.com"), make_user("a@example.com")])
    await db_session.flush()

    emails = [user.email for user in await UserRepository(db_session).list_all()]

    assert sorted(emails) == ["a@example.com", "b@example.com"]


async def test_delete_removes_user(db_session):
    user = make_user("gone@example.com")
    db_session.add(user)
    await db_session.flush()

    await UserRepository(db_session).delete(user)

    assert await UserRepository(db_session).get_by_email("gone@example.com") is None


async def test_delete_for_user_keeps_other_sessions(db_session):
    first, second = make_user("first@example.com"), make_user("second@example.com")
    db_session.add_all([first, second])
    await db_session.flush()
    db_session.add_all(
        [make_session(first, "a"), make_session(first, "b"), make_session(second, "c")]
    )
    await db_session.flush()

    await AuthSessionRepository(db_session).delete_for_user(first.id)

    left = (await db_session.scalars(select(AuthSession.user_id))).all()
    assert left == [second.id]


async def test_exists_for_user(db_session):
    user = make_user("calc@example.com")
    db_session.add(user)
    await db_session.flush()
    repository = CalculationRepository(db_session)

    assert await repository.exists_for_user(user.id) is False

    now = datetime.now(UTC)
    db_session.add(
        Calculation(
            user_id=user.id,
            requested_at=now,
            calculated_at=now,
            methodology_version="test",
            data_policy_version="test",
        )
    )
    await db_session.flush()

    assert await repository.exists_for_user(user.id) is True
