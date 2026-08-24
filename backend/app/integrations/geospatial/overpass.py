"""Bounded, factual OpenStreetMap feature discovery through Overpass."""

import asyncio
import logging
import math
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.domain.activities import ActivityKind
from app.domain.planning_areas import BoundingBox
from app.domain.routes import (
    GeoJsonLineString,
    NamedRouteReference,
    ProviderProvenance,
    RouteDiscoveryRequest,
    TrailFeature,
)
from app.integrations.routing.errors import (
    ProviderConfigurationError,
    RouteProviderMalformedResponseError,
    RouteProviderRateLimitError,
    RouteProviderTemporaryError,
    RouteProviderTimeoutError,
    UnsupportedActivityError,
)

logger = logging.getLogger(__name__)

OVERPASS_QUERY_VERSION = "1"
MAX_DISCOVERY_RADIUS_METERS = 25_000.0
EARTH_METERS_PER_DEGREE = 111_320.0
OSM_ATTRIBUTION = "© OpenStreetMap contributors"
OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"

_FOOT_KINDS = {
    ActivityKind.WALKING,
    ActivityKind.RUNNING,
    ActivityKind.TRAIL_RUNNING,
    ActivityKind.HIKING,
}
_CYCLE_KINDS = {
    ActivityKind.ROAD_CYCLING,
    ActivityKind.GRAVEL_CYCLING,
    ActivityKind.MOUNTAIN_BIKING,
}


class OverpassDiscoveryProvider:
    """Process-local cached provider; one instance serializes outbound requests."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        *,
        timeout_seconds: float = 20.0,
        cache_ttl_seconds: float = 300.0,
        cache_max_entries: int = 64,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = settings.overpass_api_url
        self._user_agent = settings.overpass_user_agent
        self._client = client
        self._timeout = timeout_seconds
        self._cache_ttl = cache_ttl_seconds
        self._cache_max = cache_max_entries
        self._clock = clock
        self._lock = asyncio.Lock()
        self._cache: OrderedDict[
            tuple[object, ...], tuple[float, list[TrailFeature]]
        ] = OrderedDict()

    async def discover(self, request: RouteDiscoveryRequest) -> list[TrailFeature]:
        bounds = normalize_discovery_bounds(request)
        key = (*bounds_key(bounds), request.activity_kind.value, OVERPASS_QUERY_VERSION)
        async with self._lock:
            cached = self._cache.get(key)
            now = self._clock()
            if cached is not None and now - cached[0] < self._cache_ttl:
                self._cache.move_to_end(key)
                return [item.model_copy(deep=True) for item in cached[1]]
            self._cache.pop(key, None)
            query = build_overpass_query(bounds, request.activity_kind)
            payload = await self._fetch(query)
            features = parse_overpass_response(payload, request.activity_kind)
            if self._cache_max > 0 and self._cache_ttl > 0:
                copies = [item.model_copy(deep=True) for item in features]
                self._cache[key] = (now, copies)
                while len(self._cache) > self._cache_max:
                    self._cache.popitem(last=False)
            return features

    async def _fetch(self, query: str) -> object:
        parsed = urlsplit(self._url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ProviderConfigurationError
        try:
            if self._client is not None:
                response = await self._client.post(
                    self._url,
                    data={"data": query},
                    headers={"User-Agent": self._user_agent},
                    timeout=self._timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        self._url,
                        data={"data": query},
                        headers={"User-Agent": self._user_agent},
                    )
        except httpx.TimeoutException as exc:
            raise RouteProviderTimeoutError from exc
        except httpx.RequestError as exc:
            raise RouteProviderTemporaryError from exc
        if response.status_code == 429:
            raise RouteProviderRateLimitError(_retry_after(response))
        if response.status_code >= 500:
            raise RouteProviderTemporaryError
        if response.status_code >= 400:
            raise ProviderConfigurationError
        try:
            return response.json()
        except ValueError as exc:
            raise RouteProviderMalformedResponseError from exc


def normalize_discovery_bounds(request: RouteDiscoveryRequest) -> BoundingBox:
    """Return at most a 50 km-wide/tall box, centered deterministically."""
    area = request.planning_area
    max_radius = MAX_DISCOVERY_RADIUS_METERS
    if request.search_radius_meters is not None:
        radius = min(request.search_radius_meters, max_radius)
        return _centered_bounds(area.latitude, area.longitude, radius)
    supplied = request.search_bounds or area.bounding_box
    if supplied is None:
        raise ProviderConfigurationError
    center_lat = area.latitude
    center_lon = area.longitude
    lat_span_m = (supplied.north - supplied.south) * EARTH_METERS_PER_DEGREE
    lon_delta = (supplied.east - supplied.west) % 360
    lon_span_m = lon_delta * EARTH_METERS_PER_DEGREE * max(
        math.cos(math.radians(center_lat)), 0.01
    )
    if lat_span_m > max_radius * 2 or lon_span_m > max_radius * 2:
        return _centered_bounds(center_lat, center_lon, max_radius)
    return supplied


def _centered_bounds(latitude: float, longitude: float, radius: float) -> BoundingBox:
    lat_delta = radius / EARTH_METERS_PER_DEGREE
    lon_delta = radius / (
        EARTH_METERS_PER_DEGREE * max(math.cos(math.radians(latitude)), 0.01)
    )
    # Avoid antimeridian-crossing syntax; clamp rather than splitting into queries.
    west = max(-180.0, longitude - lon_delta)
    east = min(180.0, longitude + lon_delta)
    return BoundingBox(
        south=max(-90.0, latitude - lat_delta),
        west=west,
        north=min(90.0, latitude + lat_delta),
        east=east,
    )


def bounds_key(bounds: BoundingBox) -> tuple[float, float, float, float]:
    return tuple(round(value, 6) for value in (
        bounds.south, bounds.west, bounds.north, bounds.east
    ))


def build_overpass_query(bounds: BoundingBox, activity: ActivityKind) -> str:
    bbox = ",".join(f"{value:.6f}" for value in (
        bounds.south, bounds.west, bounds.north, bounds.east
    ))
    if activity in _FOOT_KINDS:
        filters = [
            '[highway~"^(path|footway|pedestrian|track|bridleway|steps)$"]',
            '[foot="designated"]',
        ]
        route_types = "hiking|foot"
    elif activity in _CYCLE_KINDS:
        filters = [
            '[highway~"^(cycleway|track|path|residential|service)$"]',
            '[bicycle="designated"]',
        ]
        route_types = "bicycle|mtb"
    else:
        raise UnsupportedActivityError
    ways = "\n  ".join(f"way{item}({bbox});" for item in filters)
    return (
        f'[out:json][timeout:20];\n(\n  {ways}\n);\n'
        f'(._; relation(bw)[route~"^({route_types})$"];);\n'
        "out body geom;"
    )


def parse_overpass_response(
    payload: object, activity: ActivityKind
) -> list[TrailFeature]:
    if not isinstance(payload, Mapping):
        raise RouteProviderMalformedResponseError
    remark = payload.get("remark")
    if remark is not None:
        if not isinstance(remark, str):
            raise RouteProviderMalformedResponseError
        if remark.strip():
            normalized_remark = remark.casefold()
            if "timed out" in normalized_remark or "timeout" in normalized_remark:
                raise RouteProviderTimeoutError
            raise RouteProviderTemporaryError
    if not isinstance(payload.get("elements"), list):
        raise RouteProviderMalformedResponseError
    elements = payload["elements"]
    memberships: dict[int, list[NamedRouteReference]] = {}
    for element in elements:
        if not isinstance(element, Mapping) or element.get("type") != "relation":
            continue
        try:
            tags = _tags(element)
            route_type = tags.get("route")
            if route_type not in {"hiking", "foot", "bicycle", "mtb"}:
                continue
            relation = NamedRouteReference(
                source_id=f"relation/{int(element['id'])}",
                name=tags.get("name"), ref=tags.get("ref"),
                network=tags.get("network"), route_type=route_type,
            )
            for member in element.get("members", []):
                if isinstance(member, Mapping) and member.get("type") == "way":
                    memberships.setdefault(int(member["ref"]), []).append(relation)
        except (KeyError, TypeError, ValueError, ValidationError):
            logger.warning("Skipping malformed Overpass relation")
    results: list[TrailFeature] = []
    for element in elements:
        if not isinstance(element, Mapping) or element.get("type") != "way":
            continue
        try:
            way_id = int(element["id"])
            geometry_data = element["geometry"]
            if not isinstance(geometry_data, list):
                raise ValueError
            coordinates = []
            for node in geometry_data:
                if not isinstance(node, Mapping):
                    raise ValueError
                coordinates.append((float(node["lon"]), float(node["lat"])))
            geometry = GeoJsonLineString(coordinates=coordinates)
            tags = _tags(element)
            source_ids = [f"way/{way_id}"] + [
                route.source_id for route in memberships.get(way_id, [])
            ]
            results.append(TrailFeature(
                provider_feature_id=f"way/{way_id}",
                name=tags.get("name") or tags.get("ref"),
                geometry=geometry,
                activity_kinds=[activity],
                highway_or_way_type=tags.get("highway"),
                surface=tags.get("surface"), track_grade=tags.get("tracktype"),
                hiking_difficulty=tags.get("sac_scale"),
                mountain_bike_difficulty=tags.get("mtb:scale"),
                smoothness=tags.get("smoothness"),
                bicycle_access=tags.get("bicycle"), foot_access=tags.get("foot"),
                access=tags.get("access"),
                named_route_memberships=memberships.get(way_id, []),
                provenance=[ProviderProvenance(
                    provider="openstreetmap",
                    attribution=f"{OSM_ATTRIBUTION} — {OSM_COPYRIGHT_URL}",
                    source_ids=source_ids,
                )],
            ))
        except (KeyError, TypeError, ValueError, ValidationError):
            logger.warning("Skipping malformed Overpass way")
    return results


def _tags(element: Mapping[str, Any]) -> dict[str, str]:
    raw = element.get("tags", {})
    if not isinstance(raw, Mapping):
        raise ValueError
    return {str(key): str(value) for key, value in raw.items()}


def _retry_after(response: httpx.Response) -> int | None:
    try:
        return max(0, int(response.headers["Retry-After"]))
    except (KeyError, ValueError):
        return None
