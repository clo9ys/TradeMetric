import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Полная (грязная) цена одной бумаги в валюте:
# цена в процентах переводим в деньги через непогашенный номинал, к чистой цене добавляем НКД.
DIRTY_PRICE_SQL = (
    "CASE WHEN quote_kind = 'percent' THEN quote_value * nominal_per_bond / 100"
    " ELSE quote_value END"
    " + CASE WHEN price_type = 'clean' THEN accrued_per_bond ELSE 0 END"
)


class InstrumentSnapshot(Base):
    """Данные по бумаге, полученные от поставщика для одного расчёта. После вставки не меняются."""

    __tablename__ = "instrument_snapshots"
    __table_args__ = (
        CheckConstraint("isin ~ '^[A-Z]{2}[A-Z0-9]{9}[0-9]$'", name="isin_format"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        CheckConstraint("source IN ('cbonds', 'rudata')", name="source"),
        CheckConstraint("price_type IN ('clean', 'dirty')", name="price_type"),
        CheckConstraint("quote_kind IN ('percent', 'amount')", name="quote_kind"),
        CheckConstraint("coupon_type IN ('fixed', 'floating')", name="coupon_type"),
        CheckConstraint("quote_value > 0", name="quote_value_positive"),
        CheckConstraint("nominal_per_bond > 0", name="nominal_positive"),
        CheckConstraint("accrued_per_bond >= 0", name="accrued_not_negative"),
        CheckConstraint("coupon_frequency > 0", name="coupon_frequency_positive"),
        # обязательность полей зависит от вида данных (сноска 1 на ER-схеме)
        CheckConstraint(
            "coupon_type <> 'fixed' OR (modified_duration IS NOT NULL"
            " AND convexity IS NOT NULL AND risk_as_of_date IS NOT NULL)",
            name="fixed_has_risk",
        ),
        CheckConstraint(
            "coupon_type <> 'floating' OR coupon_frequency IS NOT NULL",
            name="floating_has_frequency",
        ),
        CheckConstraint(
            "price_type <> 'clean' OR (accrued_per_bond IS NOT NULL"
            " AND accrued_as_of_date IS NOT NULL)",
            name="clean_has_accrued",
        ),
        CheckConstraint(
            "quote_kind <> 'percent' OR nominal_per_bond IS NOT NULL",
            name="percent_has_nominal",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    isin: Mapped[str] = mapped_column(String(12))
    issue_name: Mapped[str | None] = mapped_column(Text)
    issuer_name: Mapped[str | None] = mapped_column(Text)

    source: Mapped[str] = mapped_column(String(20))
    provider_instrument_id: Mapped[str | None] = mapped_column(Text)
    quote_source: Mapped[str] = mapped_column(Text)
    price_type: Mapped[str] = mapped_column(String(20))

    quote_as_of_date: Mapped[date] = mapped_column(Date)
    quote_as_of_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    risk_as_of_date: Mapped[date | None] = mapped_column(Date)
    risk_as_of_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accrued_as_of_date: Mapped[date | None] = mapped_column(Date)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    currency: Mapped[str] = mapped_column(CHAR(3))
    nominal_per_bond: Mapped[Decimal | None] = mapped_column(Numeric)
    quote_kind: Mapped[str] = mapped_column(String(20))
    quote_value: Mapped[Decimal] = mapped_column(Numeric)
    accrued_per_bond: Mapped[Decimal | None] = mapped_column(Numeric)
    dirty_price_per_bond: Mapped[Decimal] = mapped_column(
        Numeric, Computed(DIRTY_PRICE_SQL, persisted=True)
    )

    coupon_type: Mapped[str] = mapped_column(String(20))
    coupon_frequency: Mapped[int | None] = mapped_column(SmallInteger)
    modified_duration: Mapped[Decimal | None] = mapped_column(Numeric)
    convexity: Mapped[Decimal | None] = mapped_column(Numeric)
