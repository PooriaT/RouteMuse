"""Canonical, provider-neutral route and trail facts."""

from enum import StrEnum
from math import isfinite
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.activities import ActivityKind
from app.domain.planning_areas import BoundingBox, PlanningArea

FiniteFloat = Annotated[float, Field(strict=True, allow_inf_nan=False)]
GeoJsonCoordinate = tuple[FiniteFloat, FiniteFloat] | tuple[
    FiniteFloat, FiniteFloat, FiniteFloat
]


def _validate_coordinate(coordinate: GeoJsonCoordinate) -> None:
    longitude, latitude, *elevation = coordinate
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180")
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if not all(isfinite(value) for value in (longitude, latitude, *elevation)):
        raise ValueError("coordinates must contain only finite values")


class CanonicalModel(BaseModel):
    """A strict contract that rejects unknown provider payload fields."""

    model_config = ConfigDict(extra="forbid")


class RouteShape(StrEnum):
    LOOP = "loop"
    OUT_AND_BACK = "out_and_back"
    POINT_TO_POINT = "point_to_point"


class GeoJsonLineString(CanonicalModel):
    """A WGS84 GeoJSON LineString in explicit longitude, latitude order."""

    type: Literal["LineString"] = "LineString"
    coordinates: list[GeoJsonCoordinate] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_coordinates(self) -> "GeoJsonLineString":
        for coordinate in self.coordinates:
            _validate_coordinate(coordinate)
        return self


class ProviderProvenance(CanonicalModel):
    """Provider identity and mandatory attribution retained with supplied facts."""

    provider: str = Field(min_length=1)
    attribution: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    provider_request_id: str | None = Field(default=None, min_length=1)


class NamedRouteReference(CanonicalModel):
    """Membership in a provider's named trail or route relation."""

    source_id: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1)
    ref: str | None = Field(default=None, min_length=1)
    network: str | None = Field(default=None, min_length=1)
    route_type: str | None = Field(default=None, min_length=1)


class DistanceBreakdown(CanonicalModel):
    """A normalized category's measured or proportional share of a route."""

    value: str = Field(min_length=1)
    distance_meters: float | None = Field(
        default=None, ge=0, allow_inf_nan=False, strict=True
    )
    proportion: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False, strict=True
    )

    @model_validator(mode="after")
    def require_measure(self) -> "DistanceBreakdown":
        if self.distance_meters is None and self.proportion is None:
            raise ValueError("distance_meters or proportion is required")
        return self


class SurfaceSummary(DistanceBreakdown):
    """Distance or proportion associated with a normalized surface value."""


class WayTypeSummary(DistanceBreakdown):
    """Distance or proportion associated with a normalized way type."""


class TechnicalSummary(DistanceBreakdown):
    """A distribution for difficulty, smoothness, grade, or steepness."""

    characteristic: str = Field(min_length=1)


class CandidateGenerationProvenance(CanonicalModel):
    """Inputs needed to reproduce deterministic round-trip generation later."""

    algorithm_version: str = Field(min_length=1)
    requested_distance_meters: float = Field(
        gt=0, allow_inf_nan=False, strict=True
    )
    seed: int = Field(ge=0, strict=True)
    round_trip_points: int = Field(gt=0, strict=True)


class TrailFeature(CanonicalModel):
    """A discovered geographic feature, not a generated route candidate."""

    provider_feature_id: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1)
    geometry: GeoJsonLineString
    activity_kinds: list[ActivityKind] = Field(min_length=1)
    highway_or_way_type: str | None = Field(default=None, min_length=1)
    surface: str | None = Field(default=None, min_length=1)
    track_grade: str | None = Field(default=None, min_length=1)
    hiking_difficulty: str | None = Field(default=None, min_length=1)
    mountain_bike_difficulty: str | None = Field(default=None, min_length=1)
    smoothness: str | None = Field(default=None, min_length=1)
    bicycle_access: str | None = Field(default=None, min_length=1)
    foot_access: str | None = Field(default=None, min_length=1)
    access: str | None = Field(default=None, min_length=1)
    named_route_memberships: list[NamedRouteReference] = Field(default_factory=list)
    provenance: list[ProviderProvenance] = Field(min_length=1)


class RouteDiscoveryRequest(CanonicalModel):
    """A bounded request for factual trail discovery."""

    planning_area: PlanningArea
    activity_kind: ActivityKind
    search_radius_meters: float | None = Field(
        default=None, gt=0, allow_inf_nan=False, strict=True
    )
    search_bounds: BoundingBox | None = None

    @model_validator(mode="after")
    def require_exactly_one_bound(self) -> "RouteDiscoveryRequest":
        bounds = self.search_bounds or self.planning_area.bounding_box
        if self.search_radius_meters is None and bounds is None:
            raise ValueError("a search radius or bounding box is required")
        if self.search_radius_meters is not None and self.search_bounds is not None:
            raise ValueError("use either search_radius_meters or search_bounds")
        return self


class RoundTripParameters(CanonicalModel):
    target_distance_meters: float = Field(
        gt=0, allow_inf_nan=False, strict=True
    )
    points: int = Field(gt=0, strict=True)
    seed: int = Field(ge=0, strict=True)


class RoutingRequest(CanonicalModel):
    """Narrow provider input for waypoint or deterministic round-trip routing."""

    activity_kind: ActivityKind
    coordinates: list[GeoJsonCoordinate] | None = Field(default=None, min_length=2)
    start: GeoJsonCoordinate | None = None
    round_trip: RoundTripParameters | None = None

    @model_validator(mode="after")
    def validate_mode_and_coordinates(self) -> "RoutingRequest":
        waypoint_mode = self.coordinates is not None
        round_trip_mode = self.start is not None or self.round_trip is not None
        if waypoint_mode == round_trip_mode:
            raise ValueError("choose exactly one routing mode")
        if round_trip_mode and (self.start is None or self.round_trip is None):
            raise ValueError("round-trip routing requires start and round_trip")
        for coordinate in self.coordinates or ([self.start] if self.start else []):
            _validate_coordinate(coordinate)
        return self


class RouteCandidate(CanonicalModel):
    """Provider facts plus optional, downstream-owned recommendation outputs."""

    id: UUID
    name: str = Field(min_length=1)
    activity_kind: ActivityKind
    distance_meters: float = Field(ge=0, allow_inf_nan=False, strict=True)
    estimated_duration_seconds: int | None = Field(default=None, ge=0, strict=True)
    elevation_gain_meters: float | None = Field(
        default=None, ge=0, allow_inf_nan=False, strict=True
    )
    elevation_loss_meters: float | None = Field(
        default=None, ge=0, allow_inf_nan=False, strict=True
    )
    geometry: GeoJsonLineString
    geojson_reference: str | None = Field(default=None, min_length=1)
    route_shape: RouteShape | None = None
    surface_breakdown: list[SurfaceSummary] = Field(default_factory=list)
    way_type_breakdown: list[WayTypeSummary] = Field(default_factory=list)
    technical_breakdown: list[TechnicalSummary] = Field(default_factory=list)
    provenance: list[ProviderProvenance] = Field(min_length=1)
    data_confidence: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False, strict=True
    )
    generation_provenance: CandidateGenerationProvenance | None = None
    warnings: list[str] = Field(default_factory=list)

    # These are owned by future RouteMuse scoring, never by provider adapters.
    difficulty_score: float | None = Field(default=None, ge=0, le=1)
    athlete_fit_score: float | None = Field(default=None, ge=0, le=1)
    excitement_score: float | None = Field(default=None, ge=0, le=1)
    novelty_score: float | None = Field(default=None, ge=0, le=1)
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    explanation: str | None = None

    @model_validator(mode="after")
    def validate_breakdown_totals(self) -> "RouteCandidate":
        for breakdown in (
            self.surface_breakdown,
            self.way_type_breakdown,
            self.technical_breakdown,
        ):
            proportions = [item.proportion for item in breakdown if item.proportion]
            if sum(proportions) > 1 + 1e-9:
                raise ValueError("breakdown proportions cannot total more than one")
            distances = [
                item.distance_meters for item in breakdown if item.distance_meters
            ]
            if sum(distances) > self.distance_meters + 1e-9:
                raise ValueError("breakdown distances cannot exceed route distance")
        return self
