import asyncio
from datetime import UTC, date, datetime
from typing import cast
from unittest.mock import MagicMock

import pytest

from app.db.models import (
    StravaActivity,
    StravaSynchronizationRun,
    SynchronizationStatus,
)
from app.db.repositories.strava import (
    StravaActivityUpsert,
    StravaSynchronizationRepository,
)
from app.domain.activities import ActivityKind
from app.integrations.strava.dtos import StravaActivityDTO
from app.integrations.strava.errors import (
    StravaAuthenticationInvalid,
    StravaIntegrationError,
    StravaMalformedResponse,
    StravaRateLimited,
    StravaRequestTimedOut,
    StravaTemporarilyUnavailable,
    StravaTokenRefreshFailed,
)
from app.integrations.strava.synchronization import (
    StravaSynchronizationFailed,
    StravaSynchronizationService,
    strava_calendar_bounds,
)


class FakeTokenService:
    def __init__(
        self,
        *,
        token: str = "valid-access",
        refreshed_token: str = "refreshed-access",
        usable_error: StravaIntegrationError | None = None,
        refresh_error: StravaIntegrationError | None = None,
    ) -> None:
        self.token = token
        self.refreshed_token = refreshed_token
        self.usable_error = usable_error
        self.refresh_error = refresh_error
        self.usable_calls = 0
        self.refresh_calls = 0

    async def usable_access_token(self) -> str:
        self.usable_calls += 1
        if self.usable_error is not None:
            raise self.usable_error
        return self.token

    async def refresh_access_token(self) -> str:
        self.refresh_calls += 1
        if self.refresh_error is not None:
            raise self.refresh_error
        return self.refreshed_token


class FakeStravaClient:
    def __init__(
        self,
        pages: dict[int, list[StravaActivityDTO]],
        *,
        error_on_page: dict[int, StravaIntegrationError] | None = None,
        reject_tokens: set[str] | None = None,
    ) -> None:
        self.pages = pages
        self.error_on_page = error_on_page or {}
        self.reject_tokens = reject_tokens or set()
        self.calls: list[dict[str, int | str]] = []

    async def list_activities_page(
        self,
        access_token: str,
        *,
        after: int,
        before: int,
        page: int,
        per_page: int,
    ) -> list[StravaActivityDTO]:
        self.calls.append(
            {
                "access_token": access_token,
                "after": after,
                "before": before,
                "page": page,
                "per_page": per_page,
            }
        )
        if access_token in self.reject_tokens:
            raise StravaAuthenticationInvalid("safe authentication failure")
        if page in self.error_on_page:
            raise self.error_on_page[page]
        return self.pages.get(page, [])


class InMemorySynchronizationRepository:
    def __init__(self, connection_id: int | None = 42) -> None:
        self.connection_id = connection_id
        self.activities: dict[int, StravaActivityUpsert] = {}
        self.runs: list[StravaSynchronizationRun] = []
        self.commits = 0
        self.rollbacks = 0

    def current_connection_id(self) -> int | None:
        return self.connection_id

    def create_run(
        self,
        *,
        connection_id: int,
        requested_start_at: datetime,
        requested_end_at: datetime,
    ) -> StravaSynchronizationRun:
        run = StravaSynchronizationRun(
            id=len(self.runs) + 1,
            connection_id=connection_id,
            requested_start_at=requested_start_at,
            requested_end_at=requested_end_at,
            status=SynchronizationStatus.RUNNING,
            fetched_count=0,
            inserted_count=0,
            updated_count=0,
            skipped_count=0,
        )
        self.runs.append(run)
        return run

    def upsert_page(
        self,
        *,
        connection_id: int,
        activities: list[StravaActivityUpsert],
    ) -> object:
        assert connection_id == self.connection_id
        inserted = 0
        updated = 0
        unsupported = 0
        for activity in activities:
            existing = self.activities.get(activity.strava_activity_id)
            if activity.normalized_kind is None:
                unsupported += 1
            elif existing is None:
                inserted += 1
            elif existing != activity:
                updated += 1
            self.activities[activity.strava_activity_id] = activity
        return PageCounts(inserted, updated, unsupported)

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
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class PageCounts:
    def __init__(self, inserted: int, updated: int, unsupported: int) -> None:
        self.inserted = inserted
        self.updated = updated
        self.unsupported = unsupported


def _activity(
    activity_id: int,
    *,
    sport_type: str = "Run",
    distance: float = 1_000.0,
) -> StravaActivityDTO:
    return StravaActivityDTO(
        id=activity_id,
        sport_type=sport_type,
        start_date=datetime(2026, 8, 20, 14, 30, tzinfo=UTC),
        moving_time=600,
        distance=distance,
        total_elevation_gain=25.0,
    )


def _service(
    repository: InMemorySynchronizationRepository,
    client: FakeStravaClient,
    token_service: FakeTokenService | None = None,
) -> StravaSynchronizationService:
    return StravaSynchronizationService(
        token_service=cast(object, token_service or FakeTokenService()),
        client=cast(object, client),
        repository=cast(object, repository),
        page_size=2,
    )


def _synchronize(service: StravaSynchronizationService):
    return asyncio.run(
        service.synchronize(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            timezone="America/Vancouver",
        )
    )


def test_calendar_boundaries_use_local_midnights_not_server_timezone() -> None:
    bounds = strava_calendar_bounds(
        date(2026, 7, 10), date(2026, 7, 10), "America/Vancouver"
    )

    assert bounds.start_at == datetime(2026, 7, 10, 7, tzinfo=UTC)
    assert bounds.end_at_exclusive == datetime(2026, 7, 11, 7, tzinfo=UTC)
    assert bounds.after_epoch == int(bounds.start_at.timestamp()) - 1
    assert bounds.before_epoch == int(bounds.end_at_exclusive.timestamp())


def test_calendar_boundaries_honor_dst_transition() -> None:
    bounds = strava_calendar_bounds(
        date(2026, 3, 8), date(2026, 3, 8), "America/Vancouver"
    )

    assert bounds.start_at == datetime(2026, 3, 8, 8, tzinfo=UTC)
    assert bounds.end_at_exclusive == datetime(2026, 3, 9, 7, tzinfo=UTC)
    assert (
        bounds.end_at_exclusive - bounds.start_at
    ).total_seconds() == pytest.approx(23 * 60 * 60, abs=0)


@pytest.mark.parametrize(
    ("pages", "expected_pages", "expected_fetched"),
    [
        ({1: [_activity(1)]}, 1, 1),
        ({1: [_activity(1), _activity(2)], 2: [_activity(3)]}, 2, 3),
        (
            {
                1: [_activity(1), _activity(2)],
                2: [_activity(3), _activity(4)],
                3: [],
            },
            3,
            4,
        ),
        ({1: []}, 1, 0),
    ],
)
def test_pagination_stops_on_partial_or_empty_page(
    pages: dict[int, list[StravaActivityDTO]],
    expected_pages: int,
    expected_fetched: int,
) -> None:
    repository = InMemorySynchronizationRepository()
    client = FakeStravaClient(pages)

    result = _synchronize(_service(repository, client))

    assert result.status is SynchronizationStatus.COMPLETED
    assert result.pages_fetched == expected_pages
    assert result.fetched == expected_fetched
    assert [call["page"] for call in client.calls] == list(
        range(1, expected_pages + 1)
    )
    assert repository.runs[0].status is SynchronizationStatus.COMPLETED


def test_first_sync_repeat_and_changed_activity_are_idempotent() -> None:
    repository = InMemorySynchronizationRepository()

    first = _synchronize(
        _service(repository, FakeStravaClient({1: [_activity(100)]}))
    )
    repeated = _synchronize(
        _service(repository, FakeStravaClient({1: [_activity(100)]}))
    )
    changed = _synchronize(
        _service(
            repository,
            FakeStravaClient({1: [_activity(100, distance=1_250.0)]}),
        )
    )

    assert (first.inserted, first.updated) == (1, 0)
    assert (repeated.inserted, repeated.updated) == (0, 0)
    assert (changed.inserted, changed.updated) == (0, 1)
    assert len(repository.activities) == 1
    assert repository.activities[100].distance_meters == 1_250.0


def test_supported_and_unsupported_sports_are_persisted_without_guessing() -> None:
    repository = InMemorySynchronizationRepository()
    result = _synchronize(
        _service(
            repository,
            FakeStravaClient(
                {
                    1: [
                        _activity(1, sport_type="Hike"),
                        _activity(2, sport_type="Yoga"),
                    ],
                    2: [],
                }
            ),
        )
    )

    assert result.fetched == 2
    assert result.inserted == 1
    assert result.unsupported == 1
    assert repository.activities[1].normalized_kind is ActivityKind.HIKING
    assert repository.activities[2].sport_type == "Yoga"
    assert repository.activities[2].normalized_kind is None


def test_provider_unauthorized_delegates_refresh_and_retries_same_page() -> None:
    repository = InMemorySynchronizationRepository()
    token_service = FakeTokenService(token="expired", refreshed_token="new-access")
    client = FakeStravaClient(
        {1: [_activity(1)]}, reject_tokens={"expired"}
    )

    result = _synchronize(_service(repository, client, token_service))

    assert result.status is SynchronizationStatus.COMPLETED
    assert token_service.usable_calls == 1
    assert token_service.refresh_calls == 1
    assert [call["access_token"] for call in client.calls] == [
        "expired",
        "new-access",
    ]
    assert [call["page"] for call in client.calls] == [1, 1]


def test_unrecoverable_provider_authentication_failure_is_distinct() -> None:
    repository = InMemorySynchronizationRepository()
    token_service = FakeTokenService(token="expired", refreshed_token="also-invalid")
    client = FakeStravaClient(
        {}, reject_tokens={"expired", "also-invalid"}
    )

    with pytest.raises(StravaSynchronizationFailed) as error:
        _synchronize(_service(repository, client, token_service))

    assert isinstance(error.value.cause, StravaAuthenticationInvalid)
    assert error.value.result.status is SynchronizationStatus.FAILED
    assert token_service.refresh_calls == 1
    assert repository.runs[0].status is SynchronizationStatus.FAILED


def test_initial_token_refresh_failure_marks_run_failed() -> None:
    repository = InMemorySynchronizationRepository()
    token_service = FakeTokenService(
        usable_error=StravaTokenRefreshFailed("safe refresh failure")
    )

    with pytest.raises(StravaSynchronizationFailed) as error:
        _synchronize(_service(repository, FakeStravaClient({}), token_service))

    assert isinstance(error.value.cause, StravaTokenRefreshFailed)
    assert error.value.result.status is SynchronizationStatus.FAILED
    assert error.value.result.pages_fetched == 0


def test_initial_token_refresh_rate_limit_is_preserved_for_api_translation() -> None:
    repository = InMemorySynchronizationRepository()
    rate_limit = StravaRateLimited(
        "safe token refresh rate limit", retry_after_seconds=45
    )
    token_service = FakeTokenService(usable_error=rate_limit)

    with pytest.raises(StravaSynchronizationFailed) as error:
        _synchronize(_service(repository, FakeStravaClient({}), token_service))

    assert error.value.cause is rate_limit
    assert error.value.result.status is SynchronizationStatus.FAILED
    assert error.value.result.pages_fetched == 0
    assert repository.runs[0].error_summary == "strava_rate_limited"


@pytest.mark.parametrize(
    "provider_error",
    [
        StravaRequestTimedOut("safe timeout"),
        StravaTemporarilyUnavailable("safe temporary failure"),
        StravaRateLimited("safe rate limit", retry_after_seconds=30),
        StravaMalformedResponse("safe malformed response"),
    ],
)
def test_first_page_provider_errors_mark_run_failed(
    provider_error: StravaIntegrationError,
) -> None:
    repository = InMemorySynchronizationRepository()
    client = FakeStravaClient({}, error_on_page={1: provider_error})

    with pytest.raises(StravaSynchronizationFailed) as error:
        _synchronize(_service(repository, client))

    assert error.value.cause is provider_error
    assert error.value.result.status is SynchronizationStatus.FAILED
    assert error.value.result.fetched == 0
    assert repository.runs[0].status is SynchronizationStatus.FAILED


def test_mid_pagination_failure_preserves_pages_and_reports_partial_counts() -> None:
    repository = InMemorySynchronizationRepository()
    client = FakeStravaClient(
        {
            1: [_activity(1), _activity(2, sport_type="Yoga")],
            2: [_activity(3), _activity(4)],
        },
        error_on_page={3: StravaRequestTimedOut("safe timeout")},
    )

    with pytest.raises(StravaSynchronizationFailed) as error:
        _synchronize(_service(repository, client))

    result = error.value.result
    assert result.status is SynchronizationStatus.PARTIAL
    assert result.pages_fetched == 2
    assert result.fetched == 4
    assert result.inserted == 3
    assert result.updated == 0
    assert result.unsupported == 1
    assert set(repository.activities) == {1, 2, 3, 4}
    run = repository.runs[0]
    assert run.status is SynchronizationStatus.PARTIAL
    assert run.fetched_count == 4
    assert run.error_summary == "strava_request_timed_out"

    retry = _synchronize(
        _service(
            repository,
            FakeStravaClient(
                {
                    1: [_activity(1), _activity(2, sport_type="Yoga")],
                    2: [_activity(3), _activity(4)],
                    3: [],
                }
            ),
        )
    )

    assert retry.status is SynchronizationStatus.COMPLETED
    assert retry.inserted == 0
    assert retry.updated == 0
    assert retry.unsupported == 1
    assert len(repository.activities) == 4


def test_duplicate_activity_across_pages_is_a_partial_malformed_response() -> None:
    repository = InMemorySynchronizationRepository()
    client = FakeStravaClient(
        {
            1: [_activity(1), _activity(2)],
            2: [_activity(2)],
        }
    )

    with pytest.raises(StravaSynchronizationFailed) as error:
        _synchronize(_service(repository, client))

    assert isinstance(error.value.cause, StravaMalformedResponse)
    assert error.value.result.status is SynchronizationStatus.PARTIAL
    assert error.value.result.pages_fetched == 2
    assert error.value.result.fetched == 2


def test_repository_upsert_counts_insert_update_unchanged_and_unsupported() -> None:
    session = MagicMock()
    session.scalars.return_value = []
    repository = StravaSynchronizationRepository(session)
    supported = _upsert(1, normalized_kind=ActivityKind.RUNNING)
    unsupported = _upsert(2, normalized_kind=None, sport_type="Yoga")

    first = repository.upsert_page(
        connection_id=42, activities=[supported, unsupported]
    )

    assert (first.inserted, first.updated, first.unsupported) == (1, 0, 1)
    assert session.add.call_count == 2

    stored = StravaActivity(
        connection_id=42,
        strava_activity_id=1,
        sport_type="Run",
        normalized_kind=ActivityKind.RUNNING,
        started_at=supported.started_at,
        moving_time_seconds=600,
        distance_meters=1_000.0,
        elevation_gain_meters=25.0,
    )
    session.scalars.return_value = [stored]
    unchanged = repository.upsert_page(connection_id=42, activities=[supported])
    changed = repository.upsert_page(
        connection_id=42,
        activities=[_upsert(1, normalized_kind=ActivityKind.RUNNING, distance=1_500.0)],
    )

    assert (unchanged.inserted, unchanged.updated) == (0, 0)
    assert (changed.inserted, changed.updated) == (0, 1)
    assert stored.distance_meters == 1_500.0


def _upsert(
    activity_id: int,
    *,
    normalized_kind: ActivityKind | None,
    sport_type: str = "Run",
    distance: float = 1_000.0,
) -> StravaActivityUpsert:
    return StravaActivityUpsert(
        strava_activity_id=activity_id,
        sport_type=sport_type,
        normalized_kind=normalized_kind,
        started_at=datetime(2026, 8, 20, 14, 30, tzinfo=UTC),
        moving_time_seconds=600,
        distance_meters=distance,
        elevation_gain_meters=25.0,
    )
