"""Store the exchange rate used for each calculated trade.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("calculation_trades", sa.Column("fx_rate_rub", sa.Numeric(), nullable=True))
    op.add_column("calculation_trades", sa.Column("fx_effective_date", sa.Date(), nullable=True))
    op.add_column("calculation_trades", sa.Column("fx_source", sa.String(50), nullable=True))
    op.create_check_constraint(
        op.f("ck_calculation_trades_fx_rate_positive"),
        "calculation_trades",
        "fx_rate_rub IS NULL OR fx_rate_rub > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_calculation_trades_fx_rate_positive"), "calculation_trades", type_="check"
    )
    op.drop_column("calculation_trades", "fx_source")
    op.drop_column("calculation_trades", "fx_effective_date")
    op.drop_column("calculation_trades", "fx_rate_rub")
