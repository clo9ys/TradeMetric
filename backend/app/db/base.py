from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Без явных имён Postgres сам придумает имена ограничений,
# и Alembic потом не сможет их надёжно найти при изменении схемы.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
