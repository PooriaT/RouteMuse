import asyncio
from urllib.parse import parse_qs

import httpx
import pytest

from app.integrations.strava.client import StravaClient
from app.integrations.strava.errors import (
    StravaAuthenticationInvalid,
    StravaMalformedResponse,
    StravaNetworkError,
    StravaRateLimited,
    StravaRequestTimedOut,
    StravaTemporarilyUnavailable,
)


def _activity_payload(activity_id: int = 123) -> dict[str, object]:
    return {
        "id": activity_id,
        "sport_type": "Run",
        "type": "Ride",
        "start_date": "2026-08-20T14:30:00Z",
        "moving_time": 3_601,
        "distance": 12_345.6,
        "total_elevation_gain": 789.1,
        "ignored_provider_field": "ignored",
    }


def test_activity_page_uses_typed_dto_and_expected_query_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v3/athlete/activities"
        assert parse_qs(request.url.query.decode()) == {
            "after": ["100"],
            "before": ["200"],
            "page": ["3"],
            "per_page": ["100"],
        }
        assert request.headers["Authorization"] == "Bearer access-secret"
        return httpx.Response(200, json=[_activity_payload()])

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = StravaClient(http_client)

    result = asyncio.run(
        client.list_activities_page(
            "access-secret", after=100, before=200, page=3, per_page=100
        )
    )

    assert len(result) == 1
    assert result[0].id == 123
    assert result[0].sport_type == "Run"


@pytest.mark.parametrize(
    ("status_code", "headers", "expected_error"),
    [
        (401, {}, StravaAuthenticationInvalid),
        (403, {}, StravaAuthenticationInvalid),
        (429, {"Retry-After": "90"}, StravaRateLimited),
        (500, {}, StravaTemporarilyUnavailable),
        (503, {}, StravaTemporarilyUnavailable),
    ],
)
def test_activity_page_translates_provider_statuses(
    status_code: int,
    headers: dict[str, str],
    expected_error: type[Exception],
) -> None:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status_code, headers=headers)
        )
    )
    client = StravaClient(http_client)

    with pytest.raises(expected_error) as error:
        asyncio.run(
            client.list_activities_page(
                "secret", after=1, before=2, page=1, per_page=100
            )
        )

    if isinstance(error.value, StravaRateLimited):
        assert error.value.retry_after_seconds == 90
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"not": "a list"}),
        httpx.Response(200, json=[{"id": 1}]),
        httpx.Response(200, content=b"not-json"),
        httpx.Response(400, json={"message": "provider details"}),
    ],
)
def test_activity_page_rejects_malformed_payloads_without_exposing_them(
    response: httpx.Response,
) -> None:
    client = StravaClient(
        httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response))
    )

    with pytest.raises(StravaMalformedResponse) as error:
        asyncio.run(
            client.list_activities_page(
                "secret", after=1, before=2, page=1, per_page=100
            )
        )

    assert "provider details" not in str(error.value)
    assert "secret" not in str(error.value)


def test_activity_page_translates_timeout() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("socket details", request=request)

    client = StravaClient(
        httpx.AsyncClient(transport=httpx.MockTransport(timeout))
    )

    with pytest.raises(StravaRequestTimedOut):
        asyncio.run(
            client.list_activities_page(
                "secret", after=1, before=2, page=1, per_page=100
            )
        )


def test_activity_page_translates_unexpected_network_failure() -> None:
    def network_failure(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network details", request=request)

    client = StravaClient(
        httpx.AsyncClient(transport=httpx.MockTransport(network_failure))
    )

    with pytest.raises(StravaNetworkError):
        asyncio.run(
            client.list_activities_page(
                "secret", after=1, before=2, page=1, per_page=100
            )
        )


def test_rate_limit_ignores_non_numeric_retry_after() -> None:
    client = StravaClient(
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(429, headers={"Retry-After": "later"})
            )
        )
    )

    with pytest.raises(StravaRateLimited) as error:
        asyncio.run(
            client.list_activities_page(
                "secret", after=1, before=2, page=1, per_page=100
            )
        )

    assert error.value.retry_after_seconds is None
