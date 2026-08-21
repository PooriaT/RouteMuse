from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from app.db.models import (
    StravaActivity,
    StravaConnection,
    StravaSynchronizationRun,
    SynchronizationStatus,
)
from app.db.security import TokenProtectionError
from app.domain.activities import ActivityKind


@dataclass(frozen=True)
class StravaConnectionStatus:
    athlete_id: int
    granted_scopes: list[str]


@dataclass(frozen=True, slots=True)
class StravaActivityUpsert:
    strava_activity_id: int
    sport_type: str
    normalized_kind: ActivityKind | None
    started_at: datetime
    moving_time_seconds: int
    distance_meters: float
    elevation_gain_meters: float | None


@dataclass(frozen=True, slots=True)
class StravaPageUpsertCounts:
    inserted: int
    updated: int
    unsupported: int


class StravaConnectionRepository:
    """Persistence operations used by Strava OAuth and token lifecycle services."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_current(self, *, for_update: bool = False) -> StravaConnection | None:
        statement: Select[tuple[StravaConnection]] = (
            select(StravaConnection)
            .order_by(StravaConnection.updated_at.desc(), StravaConnection.id.desc())
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        try:
            return self._session.scalar(statement)
        except StatementError as exc:
            self._raise_token_protection_error(exc)

    def get_status(self) -> StravaConnectionStatus | None:
        row = self._session.execute(
            select(
                StravaConnection.strava_athlete_id,
                StravaConnection.granted_scopes,
            )
            .order_by(StravaConnection.updated_at.desc(), StravaConnection.id.desc())
            .limit(1)
        ).one_or_none()
        if row is None:
            return None
        return StravaConnectionStatus(athlete_id=row[0], granted_scopes=row[1])

    def upsert(
        self,
        *,
        athlete_id: int,
        access_token: str,
        refresh_token: str,
        access_token_expires_at: datetime,
        granted_scopes: list[str],
    ) -> StravaConnection:
        connection = self.get_current(for_update=True)
        now = datetime.now(UTC)
        if connection is not None and connection.strava_athlete_id != athlete_id:
            # RouteMuse currently has no application-user identity. Replace the
            # singleton connection instead of leaving an older athlete available
            # to resurface after the replacement is disconnected.
            self._session.delete(connection)
            self._session.flush()
            connection = None

        if connection is None:
            connection = StravaConnection(
                singleton_slot=True,
                strava_athlete_id=athlete_id,
                access_token=access_token,
                refresh_token=refresh_token,
                access_token_expires_at=access_token_expires_at,
                granted_scopes=granted_scopes,
                connected_at=now,
                updated_at=now,
            )
            self._session.add(connection)
        else:
            connection.access_token = access_token
            connection.refresh_token = refresh_token
            connection.access_token_expires_at = access_token_expires_at
            connection.granted_scopes = granted_scopes
            connection.connected_at = now
            connection.updated_at = now
        return connection

    def delete(self, connection: StravaConnection) -> None:
        self._session.delete(connection)

    def commit(self) -> None:
        try:
            self._session.commit()
        except StatementError as exc:
            self._raise_token_protection_error(exc)

    def rollback(self) -> None:
        self._session.rollback()

    @staticmethod
    def _raise_token_protection_error(error: StatementError) -> None:
        if isinstance(error.orig, TokenProtectionError):
            raise error.orig from error
        raise error


class StravaSynchronizationRepository:
    """Bounded persistence operations for Strava synchronization pages."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def current_connection_id(self) -> int | None:
        return self._session.scalar(
            select(StravaConnection.id)
            .order_by(StravaConnection.updated_at.desc(), StravaConnection.id.desc())
            .limit(1)
        )

    def create_run(
        self,
        *,
        connection_id: int,
        requested_start_at: datetime,
        requested_end_at: datetime,
    ) -> StravaSynchronizationRun:
        run = StravaSynchronizationRun(
            connection_id=connection_id,
            requested_start_at=requested_start_at,
            requested_end_at=requested_end_at,
            status=SynchronizationStatus.RUNNING,
        )
        self._session.add(run)
        self._session.flush()
        return run

    def upsert_page(
        self,
        *,
        connection_id: int,
        activities: list[StravaActivityUpsert],
    ) -> StravaPageUpsertCounts:
        activity_ids = [activity.strava_activity_id for activity in activities]
        existing = {
            activity.strava_activity_id: activity
            for activity in self._session.scalars(
                select(StravaActivity).where(
                    StravaActivity.connection_id == connection_id,
                    StravaActivity.strava_activity_id.in_(activity_ids),
                )
            )
        }
        inserted = 0
        updated = 0
        unsupported = 0
        synchronized_at = datetime.now(UTC)

        for incoming in activities:
            stored = existing.get(incoming.strava_activity_id)
            if incoming.normalized_kind is None:
                unsupported += 1
            if stored is None:
                self._session.add(
                    StravaActivity(
                        connection_id=connection_id,
                        strava_activity_id=incoming.strava_activity_id,
                        sport_type=incoming.sport_type,
                        normalized_kind=incoming.normalized_kind,
                        started_at=incoming.started_at,
                        moving_time_seconds=incoming.moving_time_seconds,
                        distance_meters=incoming.distance_meters,
                        elevation_gain_meters=incoming.elevation_gain_meters,
                        synchronized_at=synchronized_at,
                    )
                )
                if incoming.normalized_kind is not None:
                    inserted += 1
                continue

            if not _activity_changed(stored, incoming):
                continue
            stored.sport_type = incoming.sport_type
            stored.normalized_kind = incoming.normalized_kind
            stored.started_at = incoming.started_at
            stored.moving_time_seconds = incoming.moving_time_seconds
            stored.distance_meters = incoming.distance_meters
            stored.elevation_gain_meters = incoming.elevation_gain_meters
            stored.synchronized_at = synchronized_at
            if incoming.normalized_kind is not None:
                updated += 1

        return StravaPageUpsertCounts(
            inserted=inserted,
            updated=updated,
            unsupported=unsupported,
        )

    def record_progress(
        self,
        run: StravaSynchronizationRun,
        *,
        fetched: int,
        inserted: int,
        updated: int,
        unsupported: int,
    ) -> None:
        run.fetched_count = fetched
        run.inserted_count = inserted
        run.updated_count = updated
        run.skipped_count = unsupported

    def finish_run(
        self,
        run: StravaSynchronizationRun,
        *,
        status: SynchronizationStatus,
        fetched: int,
        inserted: int,
        updated: int,
        unsupported: int,
        error_summary: str | None,
    ) -> None:
        self.record_progress(
            run,
            fetched=fetched,
            inserted=inserted,
            updated=updated,
            unsupported=unsupported,
        )
        run.status = status
        run.completed_at = datetime.now(UTC)
        run.error_summary = error_summary

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


def _activity_changed(
    stored: StravaActivity, incoming: StravaActivityUpsert
) -> bool:
    return (
        stored.sport_type != incoming.sport_type
        or stored.normalized_kind != incoming.normalized_kind
        or stored.started_at != incoming.started_at
        or stored.moving_time_seconds != incoming.moving_time_seconds
        or stored.distance_meters != incoming.distance_meters
        or stored.elevation_gain_meters != incoming.elevation_gain_meters
    )
