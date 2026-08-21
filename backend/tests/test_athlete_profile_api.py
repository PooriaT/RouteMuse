from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.routes.athlete_profile import get_athlete_profile_repository
from app.core.config import Settings
from app.db.models import StravaSynchronizationRun, SynchronizationStatus
from app.db.repositories.athlete_profile import (
    PersistedActivityHistory,
    _has_unresolved_incomplete_synchronization,
)
from app.domain.activities import ActivityKind
from app.domain.athlete_profile import ActivityAnalysisRecord
from app.main import create_app


class FakeAthleteProfileRepository:
    def __init__(
        self, history: PersistedActivityHistory | None = None
    ) -> None:
        self.history = history
        self.calls: list[dict[str, datetime]] = []

    def load_current_history(
        self, *, start_at: datetime, end_at_exclusive: datetime
    ) -> PersistedActivityHistory | None:
        self.calls.append(
            {"start_at": start_at, "end_at_exclusive": end_at_exclusive}
        )
        return self.history


def record(
    kind: ActivityKind | None,
    started_at: datetime,
    *,
    distance: float,
    moving_time: int,
    elevation: float | None,
) -> ActivityAnalysisRecord:
    return ActivityAnalysisRecord(
        activity_kind=kind,
        started_at=started_at,
        distance_meters=distance,
        moving_time_seconds=moving_time,
        elevation_gain_meters=elevation,
    )


@pytest.fixture
def mixed_history() -> PersistedActivityHistory:
    return PersistedActivityHistory(
        activities=[
            record(
                ActivityKind.ROAD_CYCLING,
                datetime(2026, 1, 10, 18, tzinfo=UTC),
                distance=60_000,
                moving_time=7_200,
                elevation=600,
            ),
            record(
                ActivityKind.ROAD_CYCLING,
                datetime(2026, 2, 10, 18, tzinfo=UTC),
                distance=80_000,
                moving_time=9_000,
                elevation=800,
            ),
            record(
                ActivityKind.ROAD_CYCLING,
                datetime(2026, 3, 20, 18, tzinfo=UTC),
                distance=100_000,
                moving_time=10_800,
                elevation=1_000,
            ),
            record(
                ActivityKind.RUNNING,
                datetime(2026, 3, 25, 18, tzinfo=UTC),
                distance=10_000,
                moving_time=3_600,
                elevation=100,
            ),
            record(
                None,
                datetime(2026, 3, 22, 18, tzinfo=UTC),
                distance=5_000,
                moving_time=1_800,
                elevation=None,
            ),
            # A defensive service boundary ensures an accidentally broad
            # persistence result still cannot leak outside the selected period.
            record(
                ActivityKind.HIKING,
                datetime(2025, 12, 1, 18, tzinfo=UTC),
                distance=12_000,
                moving_time=12_000,
                elevation=900,
            ),
        ]
    )


@pytest.fixture
def repository(
    mixed_history: PersistedActivityHistory,
) -> FakeAthleteProfileRepository:
    return FakeAthleteProfileRepository(mixed_history)


@pytest.fixture
def client(
    repository: FakeAthleteProfileRepository,
) -> Iterator[TestClient]:
    application = create_app(Settings(environment="test", _env_file=None))
    application.dependency_overrides[get_athlete_profile_repository] = (
        lambda: repository
    )
    with TestClient(application) as test_client:
        yield test_client


def profile_request() -> dict[str, str]:
    return {
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "timezone": "America/Vancouver",
    }


def test_profile_uses_current_persisted_history_and_selected_calendar_period(
    client: TestClient, repository: FakeAthleteProfileRepository
) -> None:
    response = client.post("/api/v1/athlete-profile", json=profile_request())

    assert response.status_code == 200
    assert repository.calls == [
        {
            "start_at": datetime(2026, 1, 1, 8, tzinfo=UTC),
            "end_at_exclusive": datetime(2026, 4, 1, 7, tzinfo=UTC),
        }
    ]
    payload = response.json()
    assert payload["period_start"] == "2026-01-01"
    assert payload["period_end"] == "2026-03-31"
    assert payload["timezone"] == "America/Vancouver"
    assert payload["activities_analyzed"] == 4
    assert {summary["activity_kind"] for summary in payload["activity_summaries"]} == {
        "road_cycling",
        "running",
    }


def test_profile_excludes_unsupported_activities_from_supported_metrics(
    client: TestClient,
) -> None:
    payload = client.post("/api/v1/athlete-profile", json=profile_request()).json()

    assert payload["unsupported_activities_excluded"] == 1
    assert payload["activities_analyzed"] == 4
    assert sum(
        summary["activity_count"] for summary in payload["activity_summaries"]
    ) == 4
    assert all(
        summary["activity_kind"] is not None
        for summary in payload["activity_summaries"]
    )


def test_profile_exposes_dominant_capability_and_consistency_fields(
    client: TestClient,
) -> None:
    payload = client.post("/api/v1/athlete-profile", json=profile_request()).json()

    assert payload["dominant_activity"] == {
        "activity_kind": "road_cycling",
        "total_moving_time_seconds": 27_000,
        "activity_count": 3,
        "total_distance_meters": 240_000.0,
        "moving_time_share": pytest.approx(27_000 / 30_600),
    }
    cycling = next(
        summary
        for summary in payload["activity_summaries"]
        if summary["activity_kind"] == "road_cycling"
    )
    assert cycling["capability_ranges"]["distance_meters"] == {
        "sample_size": 3,
        "p25": 70_000.0,
        "median": 80_000.0,
        "p75": 90_000.0,
        "p90": 96_000.0,
    }
    assert cycling["capability_ranges"][
        "average_moving_speed_meters_per_second"
    ]["sample_size"] == 3
    assert cycling["capability_ranges"]["pace_seconds_per_km"] is None

    consistency = next(
        signal
        for signal in payload["consistency_signals"]
        if signal["activity_kind"] == "road_cycling"
    )
    assert consistency["active_week_ratio"] == pytest.approx(3 / 14)
    assert consistency["days_since_last_activity"] == 11
    assert consistency["recency"]["baseline"] is not None
    assert consistency["recency"]["recent_to_baseline"] is not None


def test_profile_response_is_deterministic_for_fixed_history(
    client: TestClient,
) -> None:
    first = client.post("/api/v1/athlete-profile", json=profile_request())
    second = client.post("/api/v1/athlete-profile", json=profile_request())

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_empty_persisted_period_returns_typed_empty_profile(
    client: TestClient, repository: FakeAthleteProfileRepository
) -> None:
    repository.history = PersistedActivityHistory(activities=[])

    response = client.post("/api/v1/athlete-profile", json=profile_request())

    assert response.status_code == 200
    assert response.json() == {
        "period_start": "2026-01-01",
        "period_end": "2026-03-31",
        "timezone": "America/Vancouver",
        "activities_analyzed": 0,
        "unsupported_activities_excluded": 0,
        "activity_summaries": [],
        "dominant_activity": None,
        "consistency_signals": [],
    }


def test_profile_requires_the_current_strava_connection(
    client: TestClient, repository: FakeAthleteProfileRepository
) -> None:
    repository.history = None

    response = client.post("/api/v1/athlete-profile", json=profile_request())

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "code": "strava_connection_required",
            "message": "Connect Strava before building an athlete profile.",
        }
    }


def test_profile_rejects_persisted_history_from_an_incomplete_synchronization(
    client: TestClient, repository: FakeAthleteProfileRepository
) -> None:
    assert repository.history is not None
    repository.history = PersistedActivityHistory(
        activities=repository.history.activities,
        has_incomplete_synchronization=True,
    )

    response = client.post("/api/v1/athlete-profile", json=profile_request())

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "code": "athlete_profile_history_incomplete",
            "message": (
                "Complete the interrupted activity import before building "
                "a definitive athlete profile."
            ),
        }
    }


def test_later_completed_ranges_jointly_resolve_partial_coverage() -> None:
    selected_start = datetime(2026, 1, 1, tzinfo=UTC)
    split = datetime(2026, 2, 1, tzinfo=UTC)
    selected_end = datetime(2026, 3, 1, tzinfo=UTC)
    runs = [
        synchronization_run(
            1,
            SynchronizationStatus.PARTIAL,
            selected_start,
            selected_end,
        ),
        synchronization_run(
            2,
            SynchronizationStatus.COMPLETED,
            selected_start,
            split,
        ),
        synchronization_run(
            3,
            SynchronizationStatus.COMPLETED,
            split,
            selected_end,
        ),
    ]

    assert not _has_unresolved_incomplete_synchronization(
        runs,
        start_at=selected_start,
        end_at_exclusive=selected_end,
    )


def test_partial_coverage_remains_unresolved_when_completed_retry_has_a_gap() -> None:
    selected_start = datetime(2026, 1, 1, tzinfo=UTC)
    gap_start = datetime(2026, 1, 20, tzinfo=UTC)
    gap_end = datetime(2026, 2, 1, tzinfo=UTC)
    selected_end = datetime(2026, 3, 1, tzinfo=UTC)
    runs = [
        synchronization_run(
            1,
            SynchronizationStatus.PARTIAL,
            selected_start,
            selected_end,
        ),
        synchronization_run(
            2,
            SynchronizationStatus.COMPLETED,
            selected_start,
            gap_start,
        ),
        synchronization_run(
            3,
            SynchronizationStatus.COMPLETED,
            gap_end,
            selected_end,
        ),
    ]

    assert _has_unresolved_incomplete_synchronization(
        runs,
        start_at=selected_start,
        end_at_exclusive=selected_end,
    )


def test_completed_run_that_finished_before_partial_does_not_resolve_it() -> None:
    selected_start = datetime(2026, 1, 1, tzinfo=UTC)
    selected_end = datetime(2026, 3, 1, tzinfo=UTC)
    completed = synchronization_run(
        2,
        SynchronizationStatus.COMPLETED,
        selected_start,
        selected_end,
    )
    partial = synchronization_run(
        1,
        SynchronizationStatus.PARTIAL,
        selected_start,
        selected_end,
    )
    assert completed.completed_at is not None
    completed.completed_at = completed.completed_at - timedelta(days=1)

    assert _has_unresolved_incomplete_synchronization(
        [partial, completed],
        start_at=selected_start,
        end_at_exclusive=selected_end,
    )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "start_date": "2026-04-01",
            "end_date": "2026-03-31",
            "timezone": "UTC",
        },
        {
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
            "timezone": "Not/A_Timezone",
        },
    ],
)
def test_profile_reuses_controlled_calendar_period_validation(
    client: TestClient,
    repository: FakeAthleteProfileRepository,
    payload: dict[str, str],
) -> None:
    response = client.post("/api/v1/athlete-profile", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"]
    assert repository.calls == []


def synchronization_run(
    run_id: int,
    status: SynchronizationStatus,
    start_at: datetime,
    end_at: datetime,
) -> StravaSynchronizationRun:
    run = StravaSynchronizationRun(
        connection_id=1,
        requested_start_at=start_at,
        requested_end_at=end_at,
        status=status,
        completed_at=(
            None
            if status == SynchronizationStatus.RUNNING
            else datetime(2026, 4, 1, tzinfo=UTC) + timedelta(seconds=run_id)
        ),
    )
    run.id = run_id
    return run
