import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.domain.activities import ActivityKind
from app.domain.routes import RoundTripParameters, RoutingRequest
from app.integrations.routing.errors import (
    NoRouteFoundError,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderInvalidRequestError,
    RouteProviderMalformedResponseError,
    RouteProviderRateLimitError,
    RouteProviderTemporaryError,
    RouteProviderTimeoutError,
    UnsupportedActivityError,
)
from app.integrations.routing.openrouteservice import (
    ACTIVITY_PROFILES,
    OpenRouteServiceRoutingProvider,
)


def route_request(kind: ActivityKind = ActivityKind.WALKING) -> RoutingRequest:
    return RoutingRequest(
        activity_kind=kind, coordinates=[[-123.1, 49.2], [-123.2, 49.3]]
    )


def response_payload(*, elevation: bool = True) -> dict[str, Any]:
    summary: dict[str, Any] = {"distance": 4321.5, "duration": 987.6}
    if elevation:
        summary.update(ascent=321.2, descent=123.4)
    return {
        "type": "FeatureCollection",
        "metadata": {
            "attribution": "openrouteservice.org | © OpenStreetMap contributors",
            "id": "request-123",
        },
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[-123.1, 49.2, 5], [-123.2, 49.3, 20]],
            },
            "properties": {
                "summary": summary,
                "warnings": [{"code": 1, "message": "Private access may apply"}],
                "extras": {
                    "surface": {"summary": [
                        {"value": 3, "distance": 3000, "amount": 69.42},
                        {"value": 10, "distance": 1321.5, "amount": 30.58},
                    ]},
                    "waytype": {"summary": [
                        {"value": 4, "distance": 4321.5, "amount": 100}
                    ]},
                    "steepness": {"summary": [
                        {"value": 2, "distance": 2000, "amount": 46.28}
                    ]},
                    "traildifficulty": {"summary": [
                        {"value": 2, "distance": 4321.5, "amount": 100}
                    ]},
                },
            },
        }],
    }


async def invoke(
    handler: Callable[[httpx.Request], httpx.Response],
    request: RoutingRequest | None = None,
    *,
    key: str | None = "secret-key",
):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        provider = OpenRouteServiceRoutingProvider(
            Settings(openrouteservice_api_key=key), client
        )
        return await provider.route(request or route_request())
    finally:
        await client.aclose()


def test_profile_mapping_is_explicit() -> None:
    assert ACTIVITY_PROFILES == {
        ActivityKind.WALKING: "foot-walking",
        ActivityKind.HIKING: "foot-hiking",
    }


@pytest.mark.parametrize(
    ("kind", "profile"),
    [(ActivityKind.WALKING, "foot-walking"), (ActivityKind.HIKING, "foot-hiking")],
)
def test_waypoint_body_and_profile(kind: ActivityKind, profile: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=response_payload())

    asyncio.run(invoke(handler, route_request(kind)))
    assert seen[0].url.path == f"/v2/directions/{profile}/geojson"
    assert seen[0].headers["Authorization"] == "secret-key"
    body = json.loads(seen[0].content)
    assert body == {
        "coordinates": [[-123.1, 49.2], [-123.2, 49.3]],
        "elevation": True,
        "extra_info": ["surface", "waytype", "steepness", "traildifficulty"],
    }


def test_input_elevations_are_removed_from_waypoints() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=response_payload())

    request = RoutingRequest(
        activity_kind=ActivityKind.WALKING,
        coordinates=[[-123.1, 49.2, 50.0], [-123.2, 49.3, 75.0]],
    )
    asyncio.run(invoke(handler, request))

    assert seen[0]["coordinates"] == [[-123.1, 49.2], [-123.2, 49.3]]
    assert seen[0]["elevation"] is True


def test_round_trip_translation_and_seed() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=response_payload())

    request = RoutingRequest(
        activity_kind=ActivityKind.HIKING,
        start=[-123.1, 49.2],
        round_trip=RoundTripParameters(
            target_distance_meters=5000.0, points=4, seed=8675309
        ),
    )
    candidate = asyncio.run(invoke(handler, request))
    assert seen[0]["coordinates"] == [[-123.1, 49.2]]
    assert seen[0]["options"] == {
        "round_trip": {"length": 5000.0, "points": 4, "seed": 8675309}
    }
    assert candidate.distance_meters == 4321.5
    assert candidate.generation_provenance is not None
    assert candidate.generation_provenance.seed == 8675309
    assert candidate.route_shape.value == "loop"


def test_normalizes_geometry_facts_extras_warning_and_provenance() -> None:
    candidate = asyncio.run(
        invoke(lambda _: httpx.Response(200, json=response_payload()))
    )
    assert candidate.geometry.coordinates[1] == (-123.2, 49.3, 20.0)
    assert candidate.distance_meters == 4321.5
    assert candidate.estimated_duration_seconds == 988
    assert candidate.elevation_gain_meters == 321.2
    assert candidate.elevation_loss_meters == 123.4
    assert [item.value for item in candidate.surface_breakdown] == [
        "asphalt", "gravel"
    ]
    assert candidate.way_type_breakdown[0].value == "path"
    technical = [
        (item.characteristic, item.value)
        for item in candidate.technical_breakdown
    ]
    assert technical == [
        ("steepness", "moderate_incline"),
        ("trail_difficulty", "mountain_hiking"),
    ]
    assert candidate.warnings == ["Private access may apply"]
    assert candidate.provenance[0].provider == "openrouteservice"
    assert "OpenStreetMap contributors" in candidate.provenance[0].attribution
    assert candidate.provenance[0].provider_request_id == "request-123"
    assert candidate.difficulty_score is None
    assert candidate.athlete_fit_score is None
    assert candidate.excitement_score is None
    assert candidate.novelty_score is None


def test_reconciles_rounded_extra_distances_to_route_distance() -> None:
    payload = response_payload()
    feature = payload["features"][0]  # type: ignore[index]
    properties = feature["properties"]  # type: ignore[index]
    properties["summary"]["distance"] = 100.0  # type: ignore[index]
    properties["extras"]["surface"]["summary"] = [  # type: ignore[index]
        {"value": 3, "distance": 33.4},
        {"value": 10, "distance": 33.4},
        {"value": 12, "distance": 33.4},
    ]

    candidate = asyncio.run(
        invoke(lambda _: httpx.Response(200, json=payload))
    )

    distances = [item.distance_meters for item in candidate.surface_breakdown]
    assert all(distance is not None for distance in distances)
    normalized_total = sum(
        distance for distance in distances if distance is not None
    )
    assert normalized_total == pytest.approx(100.0)


def test_missing_elevation_remains_none() -> None:
    candidate = asyncio.run(invoke(
        lambda _: httpx.Response(200, json=response_payload(elevation=False))
    ))
    assert candidate.elevation_gain_meters is None
    assert candidate.elevation_loss_meters is None


def test_missing_key_and_unsupported_activity() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_payload())
    with pytest.raises(ProviderConfigurationError):
        asyncio.run(invoke(handler, key=None))
    with pytest.raises(UnsupportedActivityError):
        asyncio.run(invoke(handler, route_request(ActivityKind.RUNNING)))


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, ProviderInvalidRequestError),
        (401, ProviderAuthenticationError),
        (404, NoRouteFoundError),
        (422, NoRouteFoundError),
        (500, RouteProviderTemporaryError),
    ],
)
def test_http_errors(status: int, error: type[Exception]) -> None:
    with pytest.raises(error):
        asyncio.run(invoke(lambda _: httpx.Response(status, text="sensitive")))


def test_rate_limit_and_timeout() -> None:
    with pytest.raises(RouteProviderRateLimitError) as exc_info:
        asyncio.run(invoke(lambda _: httpx.Response(
            429, headers={"Retry-After": "12"}
        )))
    assert exc_info.value.retry_after_seconds == 12

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(RouteProviderTimeoutError):
        asyncio.run(invoke(timeout))


@pytest.mark.parametrize(
    "payload",
    [
        {
            "type": "FeatureCollection",
            "metadata": {"attribution": "ORS"},
            "features": [],
        },
        {
            "type": "FeatureCollection",
            "metadata": {"attribution": "ORS"},
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [1, 2]},
                "properties": {"summary": {"distance": 1, "duration": 1}},
            }],
        },
        {
            "type": "FeatureCollection",
            "metadata": {"attribution": "ORS"},
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "LineString", "coordinates": [[181, 2], [1, 2]]
                },
                "properties": {"summary": {"distance": 1, "duration": 1}},
            }],
        },
    ],
)
def test_malformed_geojson(payload: dict[str, Any]) -> None:
    with pytest.raises(RouteProviderMalformedResponseError):
        asyncio.run(invoke(lambda _: httpx.Response(200, json=payload)))


def test_malformed_json_and_missing_summary() -> None:
    with pytest.raises(RouteProviderMalformedResponseError):
        asyncio.run(invoke(lambda _: httpx.Response(200, content=b"not-json")))
    payload = response_payload()
    del payload["features"][0]["properties"]["summary"]  # type: ignore[index]
    with pytest.raises(RouteProviderMalformedResponseError):
        asyncio.run(invoke(lambda _: httpx.Response(200, json=payload)))
