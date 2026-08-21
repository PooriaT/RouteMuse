"""Enforce the application-wide singleton Strava connection."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The application has no user identity to scope connections by. Preserve only
    # the newest connection before adding the singleton constraint. Cascades remove
    # activity and synchronization data belonging to superseded connections.
    op.execute(
        """
        DELETE FROM strava_connections
        WHERE id NOT IN (
            SELECT id
            FROM strava_connections
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
        )
        """
    )
    op.add_column(
        "strava_connections",
        sa.Column(
            "singleton_slot",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_strava_connections_singleton",
        "strava_connections",
        "singleton_slot",
    )
    op.create_unique_constraint(
        "uq_strava_connections_singleton",
        "strava_connections",
        ["singleton_slot"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_strava_connections_singleton",
        "strava_connections",
        type_="unique",
    )
    op.drop_constraint(
        "ck_strava_connections_singleton",
        "strava_connections",
        type_="check",
    )
    op.drop_column("strava_connections", "singleton_slot")
