import argparse
import asyncio
import getpass
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.config import get_settings
from app.db.engine import DatabaseManager
from app.db.uow import UnitOfWork
from app.domain.enums import UserRole
from app.services.admin_users import AdminUserService, EmailTaken

MIN_PASSWORD_LENGTH = 8
_EMAIL = TypeAdapter(EmailStr)


def read_password() -> str:
    pswrd1 = getpass.getpass(prompt="Пароль: ")
    pswrd2 = getpass.getpass(prompt="Еще раз: ")

    if pswrd2 != pswrd1:
        sys.exit("Пароли не совпадают")
    if len(pswrd1) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов")
    return pswrd1


async def create_user(email: str, password: str, role: UserRole) -> None:
    db = DatabaseManager(get_settings().database_url)
    try:
        await AdminUserService(UnitOfWork(db.session_factory)).create_user(email, password, role)
    except EmailTaken:
        sys.exit("Пользователь с таким email уже создан")
    finally:
        await db.dispose()


def email_arg(value: str) -> str:
    # та же проверка, что у входа: иначе можно создать пользователя, который не сможет войти
    try:
        return _EMAIL.validate_python(value.strip())
    except ValidationError as exc:
        raise argparse.ArgumentTypeError(f"некорректный email: {value}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Создать пользователя TradeMetric")
    parser.add_argument("email", type=email_arg)
    parser.add_argument(
        "--admin",
        dest="role",
        action="store_const",
        const=UserRole.ADMIN,
        default=UserRole.USER,
        help="создать администратора (первого админа заводят только так)",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    asyncio.run(create_user(args.email, read_password(), args.role))
    print(f"Пользователь {args.email} создан, роль {args.role.value}")


if __name__ == "__main__":
    main()
