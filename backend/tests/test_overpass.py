import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.domain.activities import ActivityKind
from app.domain.planning_areas import BoundingBox, PlanningArea
from app.domain.routes import RouteDiscoveryRequest
from app.integrations.geospatial.overpass import (
    MAX_DISCOVERY_RADIUS_METERS,
    OverpassDiscoveryProvider,
    build_overpass_query,
    normalize_discovery_bounds,
)
from app.integrations.routing.errors import (
    ProviderConfigurationError,
    RouteProviderMalformedResponseError,
    RouteProviderRateLimitError,
    RouteProviderTemporaryError,
    RouteProviderTimeoutError,
)


def sync_test(
    function: Callable[..., Coroutine[Any, Any, None]],
) -> Callable[..., None]:
    @wraps(function)
    def wrapper(*args: object, **kwargs: object) -> None:
        asyncio.run(function(*args, **kwargs))

    return wrapper


def request(kind: ActivityKind = ActivityKind.HIKING) -> RouteDiscoveryRequest:
    return RouteDiscoveryRequest(
        planning_area=PlanningArea(
            latitude=49.25,
            longitude=-123.1,
            display_name="Vancouver",
            source_provider="test",
            source_attribution="test",
        ),
        activity_kind=kind,
        search_bounds=BoundingBox(
            south=49.2, west=-123.2, north=49.3, east=-123.0
        ),
    )


def payload() -> dict[str, object]:
    return {
        "elements": [
            {
                "type": "relation",
                "id": 9,
                "tags": {
                    "route": "hiking",
                    "name": "Coast Trail",
                    "ref": "CT",
                    "network": "lwn",
                },
                "members": [{"type": "way", "ref": 1, "role": ""}],
            },
            {
                "type": "way",
                "id": 1,
                "tags": {
                    "name": "Creek Path",
                    "ref": "P1",
                    "highway": "path",
                    "surface": "gravel",
                    "tracktype": "grade2",
                    "smoothness": "intermediate",
                    "sac_scale": "mountain_hiking",
                    "mtb:scale": "2",
                    "bicycle": "designated",
                    "foot": "yes",
                    "access": "private",
                    "lit": "no",
                    "bridge": "yes",
                },
                "geometry": [
                    {"lat": 49.2, "lon": -123.1},
                    {"lat": 49.21, "lon": -123.11},
                ],
            },
        ]
    }


def provider(handler, **kwargs) -> tuple[OverpassDiscoveryProvider, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    instance = OverpassDiscoveryProvider(Settings(), client, **kwargs)
    return instance, client


def test_query_is_bounded_and_activity_aware() -> None:
    bounds = normalize_discovery_bounds(request())
    walking = build_overpass_query(bounds, ActivityKind.HIKING)
    cycling = build_overpass_query(bounds, ActivityKind.MOUNTAIN_BIKING)
    bbox = "49.200000,-123.200000,49.300000,-123.000000"
    assert bbox in walking
    assert 'highway~"^(path|footway|pedestrian|track|bridleway|steps)$"' in walking
    assert '[foot="designated"]' in walking
    assert 'route~"^(hiking|foot)$"' in walking
    assert 'highway~"^(cycleway|track|path|residential|service)$"' in cycling
    assert '[bicycle="designated"]' in cycling
    assert 'route~"^(bicycle|mtb)$"' in cycling


def test_oversized_bounds_and_radius_are_clamped_deterministically() -> None:
    oversized = request().model_copy(
        update={"search_bounds": BoundingBox(south=-60, west=-170, north=70, east=170)}
    )
    first = normalize_discovery_bounds(oversized)
    assert first == normalize_discovery_bounds(oversized)
    assert (first.north - first.south) * 111_320 == pytest.approx(
        MAX_DISCOVERY_RADIUS_METERS * 2
    )


@sync_test
async def test_parses_way_tags_geometry_relation_and_attribution() -> None:
    seen: list[httpx.Request] = []

    def handler(http_request: httpx.Request) -> httpx.Response:
        seen.append(http_request)
        return httpx.Response(200, json=payload())

    instance, client = provider(handler)
    try:
        features = await instance.discover(request())
    finally:
        await client.aclose()
    assert len(seen) == 1
    assert seen[0].headers["User-Agent"].startswith("RouteMuse/")
    feature = features[0]
    assert feature.provider_feature_id == "way/1"
    assert feature.name == "Creek Path"
    assert feature.geometry.coordinates == [(-123.1, 49.2), (-123.11, 49.21)]
    assert (feature.surface, feature.track_grade) == ("gravel", "grade2")
    assert feature.smoothness == "intermediate"
    assert feature.hiking_difficulty == "mountain_hiking"
    assert feature.mountain_bike_difficulty == "2"
    assert (feature.bicycle_access, feature.foot_access, feature.access) == (
        "designated", "yes", "private"
    )
    membership = feature.named_route_memberships[0]
    assert (membership.source_id, membership.name, membership.ref) == (
        "relation/9", "Coast Trail", "CT"
    )
    assert (membership.network, membership.route_type) == ("lwn", "hiking")
    assert feature.provenance[0].provider == "openstreetmap"
    assert feature.provenance[0].source_ids == ["way/1", "relation/9"]
    assert "OpenStreetMap contributors" in feature.provenance[0].attribution
    assert "openstreetmap.org/copyright" in feature.provenance[0].attribution


@sync_test
async def test_missing_tags_empty_and_bad_geometry_are_safe() -> None:
    responses = iter([
        {"elements": [{"type": "way", "id": 2, "geometry": [
            {"lat": 1, "lon": 2}, {"lat": 2, "lon": 3}
        ]}]},
        {"elements": []},
        {"elements": [{"type": "way", "id": 3, "geometry": [
            {"lat": 99, "lon": 2}
        ]}]},
    ])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    instance, client = provider(handler, cache_ttl_seconds=0)
    try:
        no_tags = await instance.discover(request())
        assert no_tags[0].surface is None and no_tags[0].name is None
        assert await instance.discover(request()) == []
        assert await instance.discover(request()) == []
    finally:
        await client.aclose()


@sync_test
async def test_cache_hit_expiry_and_boundedness() -> None:
    calls = 0
    now = [0.0]

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"elements": []})

    instance, client = provider(
        handler, cache_ttl_seconds=10, cache_max_entries=1, clock=lambda: now[0]
    )
    try:
        await instance.discover(request())
        await instance.discover(request())
        assert calls == 1
        now[0] = 11
        await instance.discover(request())
        assert calls == 2
        second = request(ActivityKind.ROAD_CYCLING)
        await instance.discover(second)
        await instance.discover(request())
        assert calls == 4  # LRU entry was evicted by the second activity.
    finally:
        await client.aclose()


@sync_test
async def test_requests_are_serialized() -> None:
    active = 0
    maximum = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(200, json={"elements": []})

    instance, client = provider(handler, cache_ttl_seconds=0)
    try:
        await asyncio.gather(instance.discover(request()), instance.discover(request()))
    finally:
        await client.aclose()
    assert maximum == 1


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (
            httpx.Response(429, headers={"Retry-After": "30"}),
            RouteProviderRateLimitError,
        ),
        (httpx.Response(503), RouteProviderTemporaryError),
        (httpx.Response(200, text="not json"), RouteProviderMalformedResponseError),
        (
            httpx.Response(200, json={"not_elements": []}),
            RouteProviderMalformedResponseError,
        ),
        (httpx.Response(400), ProviderConfigurationError),
    ],
)
@sync_test
async def test_controlled_http_and_response_errors(response, error) -> None:
    instance, client = provider(lambda _: response)
    try:
        with pytest.raises(error) as caught:
            await instance.discover(request())
        if response.status_code == 429:
            assert caught.value.retry_after_seconds == 30
    finally:
        await client.aclose()


@sync_test
async def test_timeout_is_controlled_and_not_cached() -> None:
    calls = 0

    def handler(http_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow", request=http_request)

    instance, client = provider(handler)
    try:
        for _ in range(2):
            with pytest.raises(RouteProviderTimeoutError):
                await instance.discover(request())
    finally:
        await client.aclose()
    assert calls == 2
