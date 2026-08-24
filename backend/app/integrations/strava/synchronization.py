from dataclasses import dataclass
from datetime import date, datetime

from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import StravaSynchronizationRun, SynchronizationStatus
from app.db.repositories.strava import (
    StravaActivityUpsert,
    StravaSynchronizationRepository,
)
from app.domain.calendar import calendar_period_bounds
from app.integrations.strava.client import StravaClient
from app.integrations.strava.dtos import StravaActivityDTO
from app.integrations.strava.errors import (
    StravaAuthenticationInvalid,
    StravaIntegrationError,
    StravaMalformedResponse,
    StravaSynchronizationPersistenceFailed,
)
from app.integrations.strava.normalization import normalize_strava_activity
from app.integrations.strava.tokens import StravaTokenService

STRAVA_SYNC_PAGE_SIZE = 100
STRAVA_SYNC_MAX_PAGES = 10_000


class StravaSynchronizationResult(BaseModel):
    status: SynchronizationStatus
    start_date: date
    end_date: date
    pages_fetched: int = 0
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    unsupported: int = 0


class StravaSynchronizationFailed(StravaIntegrationError):
    """A controlled synchronization failure with durable progress statistics."""

    def __init__(
        self,
        *,
        cause: StravaIntegrationError,
        result: StravaSynchronizationResult,
    ) -> None:
        super().__init__("Strava activity synchronization did not complete.")
        self.cause = cause
        self.result = result


@dataclass(frozen=True, slots=True)
class StravaCalendarBounds:
    start_at: datetime
    end_at_exclusive: datetime
    after_epoch: int
    before_epoch: int


def strava_calendar_bounds(
    start_date: date, end_date: date, timezone: str
) -> StravaCalendarBounds:
    bounds = calendar_period_bounds(start_date, end_date, timezone)
    return StravaCalendarBounds(
        start_at=bounds.start_at,
        end_at_exclusive=bounds.end_at_exclusive,
        # Strava's `after` boundary is exclusive. Subtracting one second keeps an
        # activity that starts exactly at the selected local midnight.
        after_epoch=int(bounds.start_at.timestamp()) - 1,
        before_epoch=int(bounds.end_at_exclusive.timestamp()),
    )


class StravaSynchronizationService:
    def __init__(
        self,
        *,
        token_service: StravaTokenService,
        client: StravaClient,
        repository: StravaSynchronizationRepository,
        page_size: int = STRAVA_SYNC_PAGE_SIZE,
    ) -> None:
        self._token_service = token_service
        self._client = client
        self._repository = repository
        self._page_size = page_size

    async def synchronize(
        self, *, start_date: date, end_date: date, timezone: str
    ) -> StravaSynchronizationResult:
        bounds = strava_calendar_bounds(start_date, end_date, timezone)
        try:
            connection_id = self._repository.current_connection_id()
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise StravaSynchronizationPersistenceFailed(
                "The current Strava connection could not be read."
            ) from exc
        if connection_id is None:
            raise StravaAuthenticationInvalid("No Strava connection is available.")

        try:
            run = self._repository.create_run(
                connection_id=connection_id,
                requested_start_at=bounds.start_at,
                requested_end_at=bounds.end_at_exclusive,
            )
            self._repository.commit()
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise StravaSynchronizationPersistenceFailed(
                "The synchronization run could not be created."
            ) from exc

        result = StravaSynchronizationResult(
            status=SynchronizationStatus.RUNNING,
            start_date=start_date,
            end_date=end_date,
        )
        persisted_pages = 0
        try:
            access_token = await self._token_service.usable_access_token()
            page = 1
            refreshed_after_unauthorized = False
            seen_activity_ids: set[int] = set()

            while True:
                if page > STRAVA_SYNC_MAX_PAGES:
                    raise StravaMalformedResponse(
                        "Strava pagination exceeded the safety limit."
                    )
                try:
                    activities = await self._client.list_activities_page(
                        access_token,
                        after=bounds.after_epoch,
                        before=bounds.before_epoch,
                        page=page,
                        per_page=self._page_size,
                    )
                except StravaAuthenticationInvalid:
                    if refreshed_after_unauthorized:
                        raise
                    access_token = await self._token_service.refresh_access_token()
                    refreshed_after_unauthorized = True
                    continue

                result.pages_fetched += 1
                self._reject_duplicate_activities(activities, seen_activity_ids)
                if activities:
                    page_counts = self._repository.upsert_page(
                        connection_id=connection_id,
                        activities=[_activity_upsert(item) for item in activities],
                    )
                    next_fetched = result.fetched + len(activities)
                    next_inserted = result.inserted + page_counts.inserted
                    next_updated = result.updated + page_counts.updated
                    next_unsupported = result.unsupported + page_counts.unsupported
                    self._repository.record_progress(
                        run,
                        fetched=next_fetched,
                        inserted=next_inserted,
                        updated=next_updated,
                        unsupported=next_unsupported,
                    )
                    self._repository.commit()
                    result.fetched = next_fetched
                    result.inserted = next_inserted
                    result.updated = next_updated
                    result.unsupported = next_unsupported
                    persisted_pages += 1

                if len(activities) < self._page_size:
                    break
                page += 1

            result.status = SynchronizationStatus.COMPLETED
            self._finish_run(run, result=result, error_summary=None)
            return result
        except SQLAlchemyError as exc:
            self._repository.rollback()
            failure = StravaSynchronizationPersistenceFailed(
                "A synchronization page could not be persisted."
            )
            self._fail_run(run, result, persisted_pages, failure)
            raise StravaSynchronizationFailed(cause=failure, result=result) from exc
        except StravaIntegrationError as exc:
            self._repository.rollback()
            self._fail_run(run, result, persisted_pages, exc)
            raise StravaSynchronizationFailed(cause=exc, result=result) from exc

    @staticmethod
    def _reject_duplicate_activities(
        activities: list[StravaActivityDTO], seen_activity_ids: set[int]
    ) -> None:
        page_ids = [activity.id for activity in activities]
        if len(page_ids) != len(set(page_ids)) or any(
            activity_id in seen_activity_ids for activity_id in page_ids
        ):
            raise StravaMalformedResponse(
                "Strava returned duplicate activities during pagination."
            )
        seen_activity_ids.update(page_ids)

    def _fail_run(
        self,
        run: StravaSynchronizationRun,
        result: StravaSynchronizationResult,
        persisted_pages: int,
        error: StravaIntegrationError,
    ) -> None:
        result.status = (
            SynchronizationStatus.PARTIAL
            if persisted_pages > 0
            else SynchronizationStatus.FAILED
        )
        self._finish_run(run, result=result, error_summary=_safe_error_code(error))

    def _finish_run(
        self,
        run: StravaSynchronizationRun,
        *,
        result: StravaSynchronizationResult,
        error_summary: str | None,
    ) -> None:
        try:
            self._repository.finish_run(
                run,
                status=result.status,
                fetched=result.fetched,
                inserted=result.inserted,
                updated=result.updated,
                unsupported=result.unsupported,
                error_summary=error_summary,
            )
            self._repository.commit()
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise StravaSynchronizationPersistenceFailed(
                "Synchronization completion could not be recorded."
            ) from exc


def _activity_upsert(source: StravaActivityDTO) -> StravaActivityUpsert:
    normalized = normalize_strava_activity(source)
    activity = normalized.activity
    return StravaActivityUpsert(
        strava_activity_id=source.id,
        sport_type=normalized.source_sport_type,
        normalized_kind=normalized.activity_kind,
        started_at=source.start_date,
        moving_time_seconds=(
            activity.moving_time_seconds if activity is not None else source.moving_time
        ),
        distance_meters=(
            activity.distance_meters if activity is not None else source.distance
        ),
        elevation_gain_meters=(
            activity.elevation_gain_meters
            if activity is not None
            else source.total_elevation_gain
        ),
        summary_polyline=(
            source.map.summary_polyline if source.map is not None else None
        ),
    )


def _safe_error_code(error: StravaIntegrationError) -> str:
    name = type(error).__name__
    characters: list[str] = []
    for index, character in enumerate(name):
        if character.isupper() and index:
            characters.append("_")
        characters.append(character.lower())
    return "".join(characters)[:128]
