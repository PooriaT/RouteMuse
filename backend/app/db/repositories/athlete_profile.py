from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    StravaActivity,
    StravaConnection,
    StravaSynchronizationRun,
    SynchronizationStatus,
)
from app.domain.athlete_profile import ActivityAnalysisRecord


@dataclass(frozen=True, slots=True)
class PersistedActivityHistory:
    """Canonical activity facts belonging to the current Strava connection."""

    activities: list[ActivityAnalysisRecord]
    has_incomplete_synchronization: bool = False


class AthleteProfileRepository:
    """Read persisted normalized history for on-demand athlete analysis."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def load_current_history(
        self,
        *,
        start_at: datetime,
        end_at_exclusive: datetime,
        connection_id: int | None = None,
    ) -> PersistedActivityHistory | None:
        if connection_id is None:
            connection_id = self._session.scalar(
                select(StravaConnection.id)
                .order_by(
                    StravaConnection.updated_at.desc(), StravaConnection.id.desc()
                )
                .limit(1)
            )
        if connection_id is None:
            return None

        synchronization_runs = list(
            self._session.scalars(
                select(StravaSynchronizationRun)
                .where(
                    StravaSynchronizationRun.connection_id == connection_id,
                    StravaSynchronizationRun.requested_start_at < end_at_exclusive,
                    StravaSynchronizationRun.requested_end_at > start_at,
                )
                .order_by(StravaSynchronizationRun.id)
            )
        )
        if _has_unresolved_incomplete_synchronization(
            synchronization_runs,
            start_at=start_at,
            end_at_exclusive=end_at_exclusive,
        ):
            return PersistedActivityHistory(
                activities=[],
                has_incomplete_synchronization=True,
            )

        rows = self._session.execute(
            select(
                StravaActivity.normalized_kind,
                StravaActivity.started_at,
                StravaActivity.distance_meters,
                StravaActivity.moving_time_seconds,
                StravaActivity.elevation_gain_meters,
            )
            .where(
                StravaActivity.connection_id == connection_id,
                StravaActivity.started_at >= start_at,
                StravaActivity.started_at < end_at_exclusive,
            )
            .order_by(StravaActivity.started_at, StravaActivity.id)
        )
        return PersistedActivityHistory(
            activities=[
                ActivityAnalysisRecord(
                    activity_kind=row.normalized_kind,
                    started_at=row.started_at,
                    distance_meters=row.distance_meters,
                    moving_time_seconds=row.moving_time_seconds,
                    elevation_gain_meters=row.elevation_gain_meters,
                )
                for row in rows
            ]
        )


def _has_unresolved_incomplete_synchronization(
    runs: Iterable[StravaSynchronizationRun],
    *,
    start_at: datetime,
    end_at_exclusive: datetime,
) -> bool:
    """Return whether persisted rows may come from incomplete page coverage.

    A running request is always incomplete. Later completed runs resolve the
    intersecting part of an earlier partial request, and multiple completed
    ranges may jointly cover that interval.
    """

    represented_runs = list(runs)
    completed_runs = [
        run
        for run in represented_runs
        if run.status == SynchronizationStatus.COMPLETED
    ]
    for incomplete_run in represented_runs:
        if incomplete_run.status == SynchronizationStatus.RUNNING:
            return True
        if incomplete_run.status != SynchronizationStatus.PARTIAL:
            continue
        incomplete_id = incomplete_run.id
        incomplete_completed_at = incomplete_run.completed_at
        if incomplete_id is None or incomplete_completed_at is None:
            return True
        affected_start = max(start_at, incomplete_run.requested_start_at)
        affected_end = min(
            end_at_exclusive,
            incomplete_run.requested_end_at,
        )
        if affected_start >= affected_end:
            continue
        later_completed_ranges = [
            (run.requested_start_at, run.requested_end_at)
            for run in completed_runs
            if _completed_after(
                run,
                completed_at=incomplete_completed_at,
                run_id=incomplete_id,
            )
            and run.requested_start_at < affected_end
            and run.requested_end_at > affected_start
        ]
        if not _ranges_cover(
            later_completed_ranges,
            start_at=affected_start,
            end_at_exclusive=affected_end,
        ):
            return True
    return False


def _completed_after(
    run: StravaSynchronizationRun,
    *,
    completed_at: datetime,
    run_id: int,
) -> bool:
    if run.completed_at is None or run.id is None:
        return False
    return (run.completed_at, run.id) > (completed_at, run_id)


def _ranges_cover(
    ranges: Iterable[tuple[datetime, datetime]],
    *,
    start_at: datetime,
    end_at_exclusive: datetime,
) -> bool:
    covered_until = start_at
    for range_start, range_end in sorted(ranges):
        if range_end <= covered_until:
            continue
        if range_start > covered_until:
            return False
        covered_until = range_end
        if covered_until >= end_at_exclusive:
            return True
    return covered_until >= end_at_exclusive
