from sqlalchemy import BigInteger, DateTime, UniqueConstraint

from app.db.base import Base
from app.db.models import (
    StravaActivity,
    StravaConnection,
    StravaSynchronizationRun,
    SynchronizationStatus,
)


def test_strava_tables_are_registered_on_the_shared_metadata() -> None:
    assert {
        "strava_connections",
        "strava_activities",
        "strava_synchronization_runs",
    }.issubset(Base.metadata.tables)
    assert StravaConnection.metadata is Base.metadata
    assert StravaActivity.metadata is Base.metadata
    assert StravaSynchronizationRun.metadata is Base.metadata


def test_provider_identity_constraints_and_types_support_large_ids() -> None:
    connection_table = StravaConnection.__table__
    activity_table = StravaActivity.__table__

    assert isinstance(connection_table.c.id.type, BigInteger)
    assert isinstance(connection_table.c.strava_athlete_id.type, BigInteger)
    assert isinstance(activity_table.c.strava_activity_id.type, BigInteger)

    connection_unique_columns = {
        tuple(constraint.columns.keys())
        for constraint in connection_table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    activity_unique_columns = {
        tuple(constraint.columns.keys())
        for constraint in activity_table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("strava_athlete_id",) in connection_unique_columns
    assert ("connection_id", "strava_activity_id") in activity_unique_columns


def test_activity_retains_provider_sport_and_allows_unknown_normalization() -> None:
    table = StravaActivity.__table__
    unsupported_activity = StravaActivity(sport_type="Velomobile", normalized_kind=None)

    assert table.c.sport_type.nullable is False
    assert table.c.normalized_kind.nullable is True
    assert unsupported_activity.sport_type == "Velomobile"
    assert unsupported_activity.normalized_kind is None
    assert {
        "ix_strava_activities_connection_id",
        "ix_strava_activities_started_at",
        "ix_strava_activities_normalized_kind",
    }.issubset({index.name for index in table.indexes})


def test_provider_event_timestamps_are_timezone_aware() -> None:
    timestamp_columns = [
        StravaConnection.__table__.c.access_token_expires_at,
        StravaConnection.__table__.c.connected_at,
        StravaActivity.__table__.c.started_at,
        StravaActivity.__table__.c.synchronized_at,
        StravaSynchronizationRun.__table__.c.requested_start_at,
        StravaSynchronizationRun.__table__.c.requested_end_at,
        StravaSynchronizationRun.__table__.c.started_at,
        StravaSynchronizationRun.__table__.c.completed_at,
    ]

    assert all(
        isinstance(column.type, DateTime) and column.type.timezone
        for column in timestamp_columns
    )


def test_synchronization_statuses_cover_issue_ten_outcomes() -> None:
    assert {status.value for status in SynchronizationStatus} == {
        "running",
        "completed",
        "partial",
        "failed",
    }


def test_connection_repr_never_contains_tokens() -> None:
    connection = StravaConnection(
        strava_athlete_id=123,
        access_token="access-secret",
        refresh_token="refresh-secret",
    )

    representation = repr(connection)

    assert "access-secret" not in representation
    assert "refresh-secret" not in representation
