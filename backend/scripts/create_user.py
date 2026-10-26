import argparse
import asyncio
import getpass
import sys

from app.config import get_settings
from app.db.engine import DatabaseManager
from app.db.models import User
from app.db.uow import UnitOfWork
from app.security import hash_password

MIN_PASSWORD_LENGTH = 8


def read_password() -> str:
    pswrd1 = getpass.getpass(prompt="Пароль: ")
    pswrd2 = getpass.getpass(prompt="Еще раз: ")

    if pswrd2 != pswrd1:
        sys.exit("Пароли не совпадают")
    if len(pswrd1) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов")
    return pswrd1


async def create_user(email: str, password: str) -> None:
    db = DatabaseManager(get_settings().database_url)
    try:
        async with UnitOfWork(db.session_factory) as uow:
            email = email.strip().lower()
            if await uow.users.get_by_email(email):
                sys.exit("Пользователь с таким email уже создан")
            await uow.users.add(User(email=email, password_hash=hash_password(password)))
            await uow.commit()

    finally:
        await db.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Создать пользователя TradeMetric")
    parser.add_argument("email")
    args = parser.parse_args()
    asyncio.run(create_user(args.email, read_password()))
    print(f"Пользователь {args.email} создан")


if __name__ == "__main__":
    main()
