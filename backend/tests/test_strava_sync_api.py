from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.models import SynchronizationStatus
from app.integrations.strava.dependencies import get_strava_synchronization_service
from app.integrations.strava.errors import (
    StravaAuthenticationInvalid,
    StravaRateLimited,
)
from app.integrations.strava.synchronization import (
    StravaSynchronizationFailed,
    StravaSynchronizationResult,
)
from app.main import create_app


class StubSynchronizationService:
    def __init__(
        self,
        *,
        result: StravaSynchronizationResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def synchronize(
        self, *, start_date: date, end_date: date, timezone: str
    ) -> StravaSynchronizationResult:
        self.calls.append(
            {
                "start_date": start_date,
                "end_date": end_date,
                "timezone": timezone,
            }
        )
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


@pytest.fixture
def successful_service() -> StubSynchronizationService:
    return StubSynchronizationService(
        result=StravaSynchronizationResult(
            status=SynchronizationStatus.COMPLETED,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            pages_fetched=2,
            fetched=3,
            inserted=2,
            updated=0,
            unsupported=1,
        )
    )


@pytest.fixture
def client(successful_service: StubSynchronizationService) -> Iterator[TestClient]:
    application = create_app(Settings(environment="test", _env_file=None))
    application.dependency_overrides[get_strava_synchronization_service] = (
        lambda: successful_service
    )
    with TestClient(application) as test_client:
        yield test_client


def test_sync_endpoint_accepts_typed_range_and_returns_stable_statistics(
    client: TestClient, successful_service: StubSynchronizationService
) -> None:
    response = client.post(
        "/api/v1/strava/sync",
        json={
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
            "timezone": "America/Vancouver",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "start_date": "2026-08-01",
        "end_date": "2026-08-31",
        "pages_fetched": 2,
        "fetched": 3,
        "inserted": 2,
        "updated": 0,
        "unsupported": 1,
    }
    assert successful_service.calls == [
        {
            "start_date": date(2026, 8, 1),
            "end_date": date(2026, 8, 31),
            "timezone": "America/Vancouver",
        }
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"end_date": "2026-08-31", "timezone": "UTC"},
        {"start_date": "2026-08-01", "timezone": "UTC"},
        {
            "start_date": "2026-08-31",
            "end_date": "2026-08-01",
            "timezone": "UTC",
        },
        {
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
            "timezone": "Not/A_Timezone",
        },
        {
            "start_date": "not-a-date",
            "end_date": "2026-08-31",
            "timezone": "UTC",
        },
    ],
)
def test_sync_endpoint_returns_controlled_validation_errors(
    client: TestClient,
    successful_service: StubSynchronizationService,
    payload: dict[str, str],
) -> None:
    response = client.post("/api/v1/strava/sync", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"]
    assert successful_service.calls == []


def test_sync_endpoint_rejects_system_dependent_localtime_key(
    client: TestClient,
    successful_service: StubSynchronizationService,
) -> None:
    response = client.post(
        "/api/v1/strava/sync",
        json={
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
            "timezone": "localtime",
        },
    )

    assert response.status_code == 422
    assert successful_service.calls == []


def test_sync_endpoint_exposes_partial_rate_limit_progress_and_retry_metadata() -> None:
    partial = StravaSynchronizationResult(
        status=SynchronizationStatus.PARTIAL,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        pages_fetched=2,
        fetched=4,
        inserted=3,
        updated=0,
        unsupported=1,
    )
    service = StubSynchronizationService(
        error=StravaSynchronizationFailed(
            cause=StravaRateLimited(
                "safe rate limit", retry_after_seconds=120
            ),
            result=partial,
        )
    )
    application = create_app(Settings(environment="test", _env_file=None))
    application.dependency_overrides[get_strava_synchronization_service] = (
        lambda: service
    )

    with TestClient(application) as test_client:
        response = test_client.post(
            "/api/v1/strava/sync",
            json={
                "start_date": "2026-08-01",
                "end_date": "2026-08-31",
                "timezone": "UTC",
            },
        )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "120"
    assert response.json()["detail"] == {
        "code": "strava_rate_limited",
        "message": "Strava rate limits are temporarily preventing synchronization.",
        "retry_after_seconds": 120,
        "synchronization": {
            "status": "partial",
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
            "pages_fetched": 2,
            "fetched": 4,
            "inserted": 3,
            "updated": 0,
            "unsupported": 1,
        },
    }


def test_sync_endpoint_reports_unrecoverable_authentication_without_secrets() -> None:
    failed = StravaSynchronizationResult(
        status=SynchronizationStatus.FAILED,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )
    service = StubSynchronizationService(
        error=StravaSynchronizationFailed(
            cause=StravaAuthenticationInvalid("token secret-token expired"),
            result=failed,
        )
    )
    application = create_app(Settings(environment="test", _env_file=None))
    application.dependency_overrides[get_strava_synchronization_service] = (
        lambda: service
    )

    with TestClient(application) as test_client:
        response = test_client.post(
            "/api/v1/strava/sync",
            json={
                "start_date": "2026-08-01",
                "end_date": "2026-08-31",
                "timezone": "UTC",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "strava_authentication_invalid"
    assert response.json()["detail"]["synchronization"]["status"] == "failed"
    assert "secret-token" not in response.text
