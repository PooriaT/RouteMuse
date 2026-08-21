"""Add Strava connection, activity, and synchronization persistence."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


activity_kind = sa.Enum(
    "walking",
    "running",
    "trail_running",
    "hiking",
    "road_cycling",
    "gravel_cycling",
    "mountain_biking",
    "alpine_skiing",
    "backcountry_skiing",
    "nordic_skiing",
    name="routemuse_activity_kind",
    native_enum=False,
    create_constraint=True,
    length=32,
)

synchronization_status = sa.Enum(
    "running",
    "completed",
    "partial",
    "failed",
    name="strava_synchronization_status",
    native_enum=False,
    create_constraint=True,
    length=16,
)


def upgrade() -> None:
    op.create_table(
        "strava_connections",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("strava_athlete_id", sa.BigInteger(), nullable=False),
        sa.Column("access_token_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column(
            "access_token_expires_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("granted_scopes", sa.ARRAY(sa.String(length=64)), nullable=False),
        sa.Column(
            "connected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "strava_athlete_id", name="uq_strava_connections_athlete_id"
        ),
    )

    op.create_table(
        "strava_activities",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("connection_id", sa.BigInteger(), nullable=False),
        sa.Column("strava_activity_id", sa.BigInteger(), nullable=False),
        sa.Column("sport_type", sa.String(length=64), nullable=False),
        sa.Column("normalized_kind", activity_kind, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("moving_time_seconds", sa.Integer(), nullable=False),
        sa.Column("distance_meters", sa.Float(), nullable=False),
        sa.Column("elevation_gain_meters", sa.Float(), nullable=True),
        sa.Column(
            "synchronized_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "distance_meters >= 0", name="ck_strava_activities_distance"
        ),
        sa.CheckConstraint(
            "elevation_gain_meters IS NULL OR elevation_gain_meters >= 0",
            name="ck_strava_activities_elevation_gain",
        ),
        sa.CheckConstraint(
            "moving_time_seconds >= 0", name="ck_strava_activities_moving_time"
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["strava_connections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "strava_activity_id",
            name="uq_strava_activities_connection_activity",
        ),
    )
    op.create_index(
        "ix_strava_activities_connection_id",
        "strava_activities",
        ["connection_id"],
        unique=False,
    )
    op.create_index(
        "ix_strava_activities_normalized_kind",
        "strava_activities",
        ["normalized_kind"],
        unique=False,
    )
    op.create_index(
        "ix_strava_activities_started_at",
        "strava_activities",
        ["started_at"],
        unique=False,
    )

    op.create_table(
        "strava_synchronization_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("connection_id", sa.BigInteger(), nullable=False),
        sa.Column("requested_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            synchronization_status,
            server_default="running",
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("inserted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "fetched_count >= 0", name="ck_strava_sync_runs_fetched_count"
        ),
        sa.CheckConstraint(
            "inserted_count >= 0", name="ck_strava_sync_runs_inserted_count"
        ),
        sa.CheckConstraint(
            "requested_start_at <= requested_end_at",
            name="ck_strava_sync_runs_requested_range",
        ),
        sa.CheckConstraint(
            "skipped_count >= 0", name="ck_strava_sync_runs_skipped_count"
        ),
        sa.CheckConstraint(
            "updated_count >= 0", name="ck_strava_sync_runs_updated_count"
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["strava_connections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_strava_sync_runs_connection_id",
        "strava_synchronization_runs",
        ["connection_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_strava_sync_runs_connection_id",
        table_name="strava_synchronization_runs",
    )
    op.drop_table("strava_synchronization_runs")
    op.drop_index("ix_strava_activities_started_at", table_name="strava_activities")
    op.drop_index(
        "ix_strava_activities_normalized_kind", table_name="strava_activities"
    )
    op.drop_index("ix_strava_activities_connection_id", table_name="strava_activities")
    op.drop_table("strava_activities")
    op.drop_table("strava_connections")
