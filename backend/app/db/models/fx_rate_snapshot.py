import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CHAR, CheckConstraint, Date, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FXRateSnapshot(Base):
    """Неизменяемый курс, использованный одним или несколькими рядами расчёта."""

    __tablename__ = "fx_rate_snapshots"
    __table_args__ = (
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        CheckConstraint("rub_per_unit > 0", name="rate_positive"),
        CheckConstraint("effective_date <= requested_date", name="effective_not_future"),
        CheckConstraint("currency <> 'RUB' OR rub_per_unit = 1", name="rub_is_one"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    currency: Mapped[str] = mapped_column(CHAR(3))
    rub_per_unit: Mapped[Decimal] = mapped_column(Numeric)
    effective_date: Mapped[date] = mapped_column(Date)
    requested_date: Mapped[date] = mapped_column(Date)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(50))
