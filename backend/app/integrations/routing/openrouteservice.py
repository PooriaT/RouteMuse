"""OpenRouteService Directions adapter for provider-grounded foot routes."""

from typing import Any, Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings
from app.domain.activities import ActivityKind
from app.domain.routes import (
    CandidateGenerationProvenance,
    GeoJsonLineString,
    ProviderProvenance,
    RouteCandidate,
    RouteShape,
    RoutingRequest,
    SurfaceSummary,
    TechnicalSummary,
    WayTypeSummary,
)
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

DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/{profile}/geojson"
ACTIVITY_PROFILES: dict[ActivityKind, str] = {
    ActivityKind.WALKING: "foot-walking",
    ActivityKind.HIKING: "foot-hiking",
}
EXTRA_INFORMATION = ["surface", "waytype", "steepness", "traildifficulty"]

SURFACES = {
    0: "unknown", 1: "paved", 2: "unpaved", 3: "asphalt", 4: "concrete",
    5: "cobblestone", 6: "metal", 7: "wood", 8: "compacted_gravel",
    9: "fine_gravel", 10: "gravel", 11: "dirt", 12: "ground", 13: "ice",
    14: "paving_stones", 15: "sand", 16: "woodchips", 17: "grass",
    18: "grass_paving",
}
WAY_TYPES = {
    0: "unknown", 1: "state_road", 2: "road", 3: "street", 4: "path",
    5: "track", 6: "cycleway", 7: "footway", 8: "steps", 9: "ferry",
    10: "construction",
}
STEEPNESS = {
    -5: "extreme_decline", -4: "very_steep_decline", -3: "steep_decline",
    -2: "moderate_decline", -1: "gentle_decline", 0: "level",
    1: "gentle_incline", 2: "moderate_incline", 3: "steep_incline",
    4: "very_steep_incline", 5: "extreme_incline",
}
TRAIL_DIFFICULTY = {
    0: "unrated", 1: "hiking", 2: "mountain_hiking",
    3: "demanding_mountain_hiking", 4: "alpine_hiking",
    5: "demanding_alpine_hiking", 6: "difficult_alpine_hiking",
}


class _Summary(BaseModel):
    model_config = ConfigDict(extra="ignore")
    distance: float = Field(ge=0, allow_inf_nan=False)
    duration: float = Field(ge=0, allow_inf_nan=False)
    ascent: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    descent: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class _ExtraSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")
    value: int
    distance: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    amount: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)


class _Extra(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: list[_ExtraSummary] = Field(default_factory=list)


class _Warning(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: str = Field(min_length=1)


class _Properties(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: _Summary
    extras: dict[str, _Extra] = Field(default_factory=dict)
    warnings: list[_Warning] = Field(default_factory=list)


class _Geometry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["LineString"]
    coordinates: list[tuple[float, float] | tuple[float, float, float]]


class _Feature(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["Feature"]
    geometry: _Geometry
    properties: _Properties


class _Metadata(BaseModel):
    model_config = ConfigDict(extra="ignore")
    attribution: str = Field(min_length=1)
    id: str | None = None


class _FeatureCollection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["FeatureCollection"]
    features: list[_Feature] = Field(min_length=1)
    metadata: _Metadata


class OpenRouteServiceRoutingProvider:
    """Translate typed RouteMuse requests to ORS Directions GeoJSON."""

    def __init__(
        self, settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        key = settings.openrouteservice_api_key
        self._api_key = key.get_secret_value() if key is not None else None
        self._client = client

    async def route(self, request: RoutingRequest) -> RouteCandidate:
        if not self._api_key:
            raise ProviderConfigurationError
        try:
            profile = ACTIVITY_PROFILES[request.activity_kind]
        except KeyError as exc:
            raise UnsupportedActivityError from exc

        body: dict[str, Any] = {
            "coordinates": _ors_coordinates(request),
            "elevation": True,
            "extra_info": EXTRA_INFORMATION,
        }
        if request.round_trip is not None:
            body["options"] = {"round_trip": {
                "length": request.round_trip.target_distance_meters,
                "points": request.round_trip.points,
                "seed": request.round_trip.seed,
            }}

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=20.0)
        try:
            response = await client.post(
                DIRECTIONS_URL.format(profile=profile),
                headers={"Authorization": self._api_key},
                json=body,
            )
        except httpx.TimeoutException as exc:
            raise RouteProviderTimeoutError from exc
        except httpx.RequestError as exc:
            raise RouteProviderTemporaryError from exc
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError
        if response.status_code == 429:
            raise RouteProviderRateLimitError(_retry_after(response))
        if response.status_code >= 500:
            raise RouteProviderTemporaryError
        if response.status_code in {404, 422}:
            raise NoRouteFoundError
        if response.is_error:
            raise ProviderInvalidRequestError

        try:
            payload = _FeatureCollection.model_validate(response.json())
            return self._normalize(payload, request)
        except (ValueError, TypeError, ValidationError) as exc:
            raise RouteProviderMalformedResponseError from exc

    @staticmethod
    def _normalize(
        payload: _FeatureCollection, request: RoutingRequest
    ) -> RouteCandidate:
        feature = payload.features[0]
        summary = feature.properties.summary
        geometry = GeoJsonLineString(
            type=feature.geometry.type, coordinates=feature.geometry.coordinates
        )
        extras = feature.properties.extras
        generation = None
        shape = RouteShape.POINT_TO_POINT
        if request.round_trip is not None:
            shape = RouteShape.LOOP
            generation = CandidateGenerationProvenance(
                algorithm_version="openrouteservice-round-trip-v1",
                requested_distance_meters=request.round_trip.target_distance_meters,
                seed=request.round_trip.seed,
                round_trip_points=request.round_trip.points,
            )
        return RouteCandidate(
            id=uuid4(),
            name=f"openrouteservice {request.activity_kind.value} route",
            activity_kind=request.activity_kind,
            distance_meters=summary.distance,
            estimated_duration_seconds=round(summary.duration),
            elevation_gain_meters=summary.ascent,
            elevation_loss_meters=summary.descent,
            geometry=geometry,
            route_shape=shape,
            surface_breakdown=_categorical(
                extras.get("surface"), SURFACES, summary.distance
            ),
            way_type_breakdown=_categorical(
                extras.get("waytype"), WAY_TYPES, summary.distance
            ),
            technical_breakdown=[
                *_technical(
                    extras.get("steepness"),
                    "steepness",
                    STEEPNESS,
                    summary.distance,
                ),
                *_technical(
                    extras.get("traildifficulty"),
                    "trail_difficulty",
                    TRAIL_DIFFICULTY,
                    summary.distance,
                ),
            ],
            provenance=[ProviderProvenance(
                provider="openrouteservice",
                attribution=payload.metadata.attribution,
                provider_request_id=payload.metadata.id,
            )],
            generation_provenance=generation,
            warnings=[warning.message for warning in feature.properties.warnings],
        )


def _ors_coordinates(request: RoutingRequest) -> list[list[float]]:
    """Reduce canonical 2D/3D positions to ORS's longitude/latitude input."""
    coordinates = request.coordinates
    if coordinates is None:
        # RoutingRequest validation guarantees start is present in round-trip mode.
        assert request.start is not None
        coordinates = [request.start]
    return [[coordinate[0], coordinate[1]] for coordinate in coordinates]


def _measures(
    extra: _Extra, route_distance: float
) -> list[dict[str, float]]:
    """Reconcile independently rounded ORS breakdowns with route totals."""
    measures = [
        {"distance_meters": item.distance}
        if item.distance is not None
        else {"proportion": item.amount / 100}
        if item.amount is not None
        else {}
        for item in extra.summary
    ]
    distance_total = sum(
        measure.get("distance_meters", 0.0) for measure in measures
    )
    if distance_total > route_distance:
        factor = route_distance / distance_total
        for measure in measures:
            if "distance_meters" in measure:
                measure["distance_meters"] *= factor
    proportion_total = sum(measure.get("proportion", 0.0) for measure in measures)
    if proportion_total > 1:
        for measure in measures:
            if "proportion" in measure:
                measure["proportion"] /= proportion_total
    return measures


def _categorical(
    extra: _Extra | None, labels: dict[int, str], route_distance: float
) -> list[SurfaceSummary] | list[WayTypeSummary]:
    if extra is None:
        return []
    model = SurfaceSummary if labels is SURFACES else WayTypeSummary
    return [
        model(value=labels.get(item.value, f"unknown_{item.value}"), **measure)
        for item, measure in zip(
            extra.summary, _measures(extra, route_distance), strict=True
        )
        if measure
    ]


def _technical(
    extra: _Extra | None,
    characteristic: str,
    labels: dict[int, str],
    route_distance: float,
) -> list[TechnicalSummary]:
    if extra is None:
        return []
    return [
        TechnicalSummary(
            characteristic=characteristic,
            value=labels.get(item.value, f"unknown_{item.value}"),
            **measure,
        )
        for item, measure in zip(
            extra.summary, _measures(extra, route_distance), strict=True
        )
        if measure
    ]


def _retry_after(response: httpx.Response) -> int | None:
    try:
        return int(response.headers["Retry-After"])
    except (KeyError, ValueError):
        return None
