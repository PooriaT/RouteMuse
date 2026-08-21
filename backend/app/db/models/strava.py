from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.security import EncryptedToken
from app.domain.activities import ActivityKind


class SynchronizationStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


activity_kind_type = Enum(
    ActivityKind,
    values_callable=lambda kinds: [kind.value for kind in kinds],
    name="routemuse_activity_kind",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    length=32,
)

synchronization_status_type = Enum(
    SynchronizationStatus,
    values_callable=lambda statuses: [status.value for status in statuses],
    name="strava_synchronization_status",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    length=16,
)


class StravaConnection(Base):
    __tablename__ = "strava_connections"
    __table_args__ = (
        UniqueConstraint("strava_athlete_id", name="uq_strava_connections_athlete_id"),
        UniqueConstraint("singleton_slot", name="uq_strava_connections_singleton"),
        CheckConstraint("singleton_slot", name="ck_strava_connections_singleton"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    singleton_slot: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    strava_athlete_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    access_token: Mapped[str] = mapped_column(
        "access_token_ciphertext", EncryptedToken(), nullable=False
    )
    refresh_token: Mapped[str] = mapped_column(
        "refresh_token_ciphertext", EncryptedToken(), nullable=False
    )
    access_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    granted_scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list
    )
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"StravaConnection(id={self.id!r}, "
            f"strava_athlete_id={self.strava_athlete_id!r})"
        )


class StravaActivity(Base):
    __tablename__ = "strava_activities"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "strava_activity_id",
            name="uq_strava_activities_connection_activity",
        ),
        CheckConstraint(
            "moving_time_seconds >= 0", name="ck_strava_activities_moving_time"
        ),
        CheckConstraint("distance_meters >= 0", name="ck_strava_activities_distance"),
        CheckConstraint(
            "elevation_gain_meters IS NULL OR elevation_gain_meters >= 0",
            name="ck_strava_activities_elevation_gain",
        ),
        Index("ix_strava_activities_connection_id", "connection_id"),
        Index("ix_strava_activities_started_at", "started_at"),
        Index("ix_strava_activities_normalized_kind", "normalized_kind"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("strava_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    strava_activity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sport_type: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_kind: Mapped[ActivityKind | None] = mapped_column(
        activity_kind_type, nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    moving_time_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_meters: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_gain_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    synchronized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class StravaSynchronizationRun(Base):
    __tablename__ = "strava_synchronization_runs"
    __table_args__ = (
        CheckConstraint(
            "requested_start_at <= requested_end_at",
            name="ck_strava_sync_runs_requested_range",
        ),
        CheckConstraint("fetched_count >= 0", name="ck_strava_sync_runs_fetched_count"),
        CheckConstraint(
            "inserted_count >= 0", name="ck_strava_sync_runs_inserted_count"
        ),
        CheckConstraint("updated_count >= 0", name="ck_strava_sync_runs_updated_count"),
        CheckConstraint("skipped_count >= 0", name="ck_strava_sync_runs_skipped_count"),
        Index("ix_strava_sync_runs_connection_id", "connection_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("strava_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    requested_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[SynchronizationStatus] = mapped_column(
        synchronization_status_type,
        nullable=False,
        default=SynchronizationStatus.RUNNING,
        server_default=SynchronizationStatus.RUNNING.value,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fetched_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    inserted_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    updated_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
