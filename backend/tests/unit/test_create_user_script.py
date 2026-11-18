import pytest

from app.domain.enums import UserRole
from scripts.create_user import parse_args


def test_create_user_defaults_to_regular_user():
    args = parse_args(["max@example.com"])

    assert args.email == "max@example.com"
    assert args.role is UserRole.USER


def test_create_user_admin_flag_makes_admin():
    assert parse_args(["max@example.com", "--admin"]).role is UserRole.ADMIN


def test_create_user_rejects_email_that_login_would_reject():
    # служебный домен .local проходит простую проверку, но вход его не примет
    with pytest.raises(SystemExit):
        parse_args(["admin@trademetric.local"])
    with pytest.raises(SystemExit):
        parse_args(["not-an-email"])
