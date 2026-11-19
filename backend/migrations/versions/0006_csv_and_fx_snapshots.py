"""Add CSV source and immutable FX provenance.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_instrument_snapshots_source"), "instrument_snapshots", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_instrument_snapshots_source"),
        "instrument_snapshots",
        "source IN ('cbonds', 'rudata', 'demo', 'csv')",
    )
    op.create_table(
        "fx_rate_snapshots",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.Column("rub_per_unit", sa.Numeric(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("requested_date", sa.Date(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fx_rate_snapshots")),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name=op.f("ck_fx_rate_snapshots_currency_format")
        ),
        sa.CheckConstraint("rub_per_unit > 0", name=op.f("ck_fx_rate_snapshots_rate_positive")),
        sa.CheckConstraint(
            "effective_date <= requested_date",
            name=op.f("ck_fx_rate_snapshots_effective_not_future"),
        ),
        sa.CheckConstraint(
            "currency <> 'RUB' OR rub_per_unit = 1", name=op.f("ck_fx_rate_snapshots_rub_is_one")
        ),
    )
    # Старые расчёты сохраняются: время получения их курса неизвестно, не выдумываем его.
    op.add_column("calculation_trades", sa.Column("fx_snapshot_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_calculation_trades_fx_snapshot_id_fx_rate_snapshots"),
        "calculation_trades",
        "fx_rate_snapshots",
        ["fx_snapshot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_calculation_trades_fx_snapshot_id"), "calculation_trades", ["fx_snapshot_id"]
    )


def downgrade() -> None:
    # При наличии csv-снимков это ограничение остановит откат без удаления данных.
    op.drop_constraint(
        op.f("ck_instrument_snapshots_source"), "instrument_snapshots", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_instrument_snapshots_source"),
        "instrument_snapshots",
        "source IN ('cbonds', 'rudata', 'demo')",
    )
    op.drop_index(op.f("ix_calculation_trades_fx_snapshot_id"), table_name="calculation_trades")
    op.drop_constraint(
        op.f("fk_calculation_trades_fx_snapshot_id_fx_rate_snapshots"),
        "calculation_trades",
        type_="foreignkey",
    )
    op.drop_column("calculation_trades", "fx_snapshot_id")
    op.drop_table("fx_rate_snapshots")
