import uuid

from sqlalchemy import CheckConstraint

from app.api.schemas.auth import UserOut
from app.db.models import User
from app.domain.enums import UserRole


def test_user_roles_are_user_and_admin():
    assert [role.value for role in UserRole] == ["user", "admin"]


def test_user_out_exposes_role():
    user = User(
        id=uuid.uuid4(), email="max@example.com", password_hash="x", role=UserRole.ADMIN.value
    )

    assert UserOut.model_validate(user).role == "admin"


def test_users_table_allows_only_known_roles():
    table = User.metadata.tables["users"]
    checks = [str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)]

    assert "role IN ('user', 'admin')" in checks
