"""Allow signed trade quantities.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("instrument_snapshots", "dirty_price_per_bond")
    op.drop_constraint(
        op.f("ck_calculation_trades_quantity_positive"), "calculation_trades", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_calculation_trades_quantity_nonzero"), "calculation_trades", "quantity <> 0"
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_calculation_trades_quantity_nonzero"), "calculation_trades", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_calculation_trades_quantity_positive"), "calculation_trades", "quantity > 0"
    )
    op.add_column(
        "instrument_snapshots",
        sa.Column(
            "dirty_price_per_bond",
            sa.Numeric(),
            sa.Computed(
                "CASE WHEN quote_kind = 'percent' THEN quote_value * nominal_per_bond / 100"
                " ELSE quote_value END"
                " + CASE WHEN price_type = 'clean' THEN accrued_per_bond ELSE 0 END",
                persisted=True,
            ),
            nullable=False,
        ),
    )
