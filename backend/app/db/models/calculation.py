from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.calculation_trade import CalculationTrade


class Calculation(Base):
    """Завершённый расчёт. Пишется один раз вместе со сделками и больше не меняется."""

    __tablename__ = "calculations"
    __table_args__ = (
        CheckConstraint("calculated_at >= requested_at", name="calculated_after_requested"),
        CheckConstraint("jsonb_typeof(warnings) = 'array'", name="warnings_is_array"),
        # история пользователя: его расчёты от новых к старым
        Index("ix_calculations_user_id_requested_at", "user_id", text("requested_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    methodology_version: Mapped[str] = mapped_column(String(30))
    data_policy_version: Mapped[str] = mapped_column(String(30))
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )

    trades: Mapped[list[CalculationTrade]] = relationship(
        back_populates="calculation",
        order_by="CalculationTrade.line_number",
        lazy="raise",
    )
