"""Allow explicitly labeled synthetic snapshots for demonstrations.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_instrument_snapshots_source"), "instrument_snapshots", type_="check")
    op.create_check_constraint(
        op.f("ck_instrument_snapshots_source"),
        "instrument_snapshots",
        "source IN ('cbonds', 'rudata', 'demo')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_instrument_snapshots_source"), "instrument_snapshots", type_="check")
    op.create_check_constraint(
        op.f("ck_instrument_snapshots_source"),
        "instrument_snapshots",
        "source IN ('cbonds', 'rudata')",
    )
