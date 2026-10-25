from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.calculation import Calculation
from app.db.models.instrument_snapshot import InstrumentSnapshot


class CalculationTrade(Base):
    """Одна гипотетическая сделка внутри расчёта и её результат."""

    __tablename__ = "calculation_trades"
    __table_args__ = (
        UniqueConstraint("calculation_id", "client_trade_id"),
        UniqueConstraint("calculation_id", "line_number"),
        CheckConstraint("quantity <> 0", name="quantity_nonzero"),
        CheckConstraint("line_number > 0", name="line_number_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    calculation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calculations.id", ondelete="CASCADE")
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instrument_snapshots.id", ondelete="RESTRICT"), index=True
    )
    # id строки с фронта: по нему фронт сопоставляет результат со своей строкой
    client_trade_id: Mapped[uuid.UUID]
    line_number: Mapped[int]
    quantity: Mapped[int] = mapped_column(BigInteger)

    current_fair_value: Mapped[Decimal] = mapped_column(Numeric)
    duration_used: Mapped[Decimal] = mapped_column(Numeric)
    convexity_used: Mapped[Decimal] = mapped_column(Numeric)
    dv01: Mapped[Decimal] = mapped_column(Numeric)

    calculation: Mapped[Calculation] = relationship(back_populates="trades", lazy="raise")
    snapshot: Mapped[InstrumentSnapshot] = relationship(lazy="raise")
