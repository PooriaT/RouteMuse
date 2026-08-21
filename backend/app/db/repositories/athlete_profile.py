from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import StravaActivity, StravaConnection
from app.domain.athlete_profile import ActivityAnalysisRecord


@dataclass(frozen=True, slots=True)
class PersistedActivityHistory:
    """Canonical activity facts belonging to the current Strava connection."""

    activities: list[ActivityAnalysisRecord]


class AthleteProfileRepository:
    """Read persisted normalized history for on-demand athlete analysis."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def load_current_history(
        self,
        *,
        start_at: datetime,
        end_at_exclusive: datetime,
    ) -> PersistedActivityHistory | None:
        connection_id = self._session.scalar(
            select(StravaConnection.id)
            .order_by(StravaConnection.updated_at.desc(), StravaConnection.id.desc())
            .limit(1)
        )
        if connection_id is None:
            return None

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
