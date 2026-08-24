"""add nullable Strava summary polyline

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "strava_activities",
        sa.Column("summary_polyline", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("strava_activities", "summary_polyline")
