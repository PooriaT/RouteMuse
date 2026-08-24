from typing import Protocol, runtime_checkable
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.activities import ActivityKind
from app.domain.planning_areas import PlanningArea
from app.domain.routes import (
    GeoJsonLineString,
    ProviderProvenance,
    RoundTripParameters,
    RouteCandidate,
    RouteDiscoveryRequest,
    RoutingRequest,
    SurfaceSummary,
    TechnicalSummary,
    TrailFeature,
    WayTypeSummary,
)
from app.integrations.contracts import RouteDiscoveryProvider, RoutingProvider


def provenance() -> ProviderProvenance:
    return ProviderProvenance(
        provider="example", attribution="Data © Example", source_ids=["way/1"]
    )


def geometry() -> GeoJsonLineString:
    return GeoJsonLineString(coordinates=[[-123.1, 49.2], [-123.2, 49.3]])


def test_linestring_accepts_2d_coordinates() -> None:
    line = geometry()
    assert line.type == "LineString"
    assert line.coordinates[0] == (-123.1, 49.2)


def test_linestring_accepts_3d_elevation_coordinates() -> None:
    line = GeoJsonLineString(coordinates=[[-123.1, 49.2, 10], [-123.2, 49.3, 20]])
    assert line.coordinates[1][2] == 20


@pytest.mark.parametrize(
    "coordinates",
    [
        [[0.0, 91.0], [0.0, 0.0]],
        [[181.0, 0.0], [0.0, 0.0]],
        [[0.0, 0.0]],
        [[0.0, 0.0], [float("inf"), 1.0]],
    ],
)
def test_linestring_rejects_invalid_coordinates(
    coordinates: list[list[float]],
) -> None:
    with pytest.raises(ValidationError):
        GeoJsonLineString(coordinates=coordinates)


def test_trail_feature_requires_activity_and_attributed_provenance() -> None:
    feature = TrailFeature(
        provider_feature_id="way/1",
        geometry=geometry(),
        activity_kinds=[ActivityKind.HIKING],
        surface="gravel",
        provenance=[provenance()],
    )
    assert feature.surface == "gravel"

    with pytest.raises(ValidationError):
        TrailFeature(
            provider_feature_id="way/1",
            geometry=geometry(),
            activity_kinds=[],
            provenance=[],
        )
    with pytest.raises(ValidationError):
        ProviderProvenance(provider="example", attribution="")


def test_breakdowns_require_a_valid_measure() -> None:
    assert SurfaceSummary(value="unpaved", proportion=0.4).proportion == 0.4
    assert WayTypeSummary(value="path", distance_meters=500).distance_meters == 500
    assert TechnicalSummary(
        characteristic="steepness", value="moderate", proportion=0.2
    ).characteristic == "steepness"
    with pytest.raises(ValidationError):
        SurfaceSummary(value="paved")
    with pytest.raises(ValidationError):
        WayTypeSummary(value="track", proportion=1.1)


def test_routing_request_supports_waypoint_mode() -> None:
    request = RoutingRequest(
        activity_kind=ActivityKind.ROAD_CYCLING,
        coordinates=[[-123.1, 49.2], [-123.2, 49.3]],
    )
    assert request.round_trip is None


def test_routing_request_supports_round_trip_mode() -> None:
    request = RoutingRequest(
        activity_kind=ActivityKind.HIKING,
        start=[-123.1, 49.2],
        round_trip=RoundTripParameters(
            target_distance_meters=10_000, points=3, seed=42
        ),
    )
    assert request.round_trip is not None
    assert request.round_trip.seed == 42


@pytest.mark.parametrize(
    "parameters",
    [
        {"target_distance_meters": 0, "points": 3, "seed": 1},
        {"target_distance_meters": 1000, "points": 0, "seed": 1},
        {"target_distance_meters": 1000, "points": 3, "seed": -1},
    ],
)
def test_round_trip_rejects_invalid_parameters(parameters: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        RoundTripParameters(**parameters)


def test_routing_request_rejects_mixed_or_incomplete_modes() -> None:
    with pytest.raises(ValidationError):
        RoutingRequest(activity_kind=ActivityKind.HIKING)
    with pytest.raises(ValidationError):
        RoutingRequest(
            activity_kind=ActivityKind.HIKING,
            coordinates=[[0.0, 0.0], [1.0, 1.0]],
            start=[0.0, 0.0],
            round_trip=RoundTripParameters(
                target_distance_meters=1000, points=2, seed=1
            ),
        )


def test_discovery_request_must_be_spatially_bounded() -> None:
    area = PlanningArea(
        latitude=49.2,
        longitude=-123.1,
        display_name="Vancouver",
        source_provider="example",
        source_attribution="Data © Example",
    )
    with pytest.raises(ValidationError):
        RouteDiscoveryRequest(planning_area=area, activity_kind=ActivityKind.HIKING)
    request = RouteDiscoveryRequest(
        planning_area=area,
        activity_kind=ActivityKind.HIKING,
        search_radius_meters=5000,
    )
    assert request.search_radius_meters == 5000


@runtime_checkable
class _DiscoveryCheck(Protocol):
    async def discover(self, request: RouteDiscoveryRequest) -> list[TrailFeature]: ...


@runtime_checkable
class _RoutingCheck(Protocol):
    async def route(self, request: RoutingRequest) -> RouteCandidate: ...


class CompatibleProvider:
    async def discover(self, request: RouteDiscoveryRequest) -> list[TrailFeature]:
        return []

    async def route(self, request: RoutingRequest) -> RouteCandidate:
        raise NotImplementedError


def test_provider_protocols_accept_typed_implementations() -> None:
    provider = CompatibleProvider()
    discovery_contract: RouteDiscoveryProvider = provider
    routing_contract: RoutingProvider = provider
    assert isinstance(discovery_contract, _DiscoveryCheck)
    assert isinstance(routing_contract, _RoutingCheck)


def test_provider_facts_leave_recommendation_fields_unset() -> None:
    candidate = RouteCandidate(
        id=uuid4(),
        name="Provider route",
        activity_kind=ActivityKind.HIKING,
        distance_meters=2000,
        geometry=geometry(),
        provenance=[provenance()],
        data_confidence=0.8,
    )
    assert candidate.data_confidence == 0.8
    assert candidate.difficulty_score is None
    assert candidate.athlete_fit_score is None
    assert candidate.excitement_score is None
    assert candidate.novelty_score is None
    assert candidate.confidence_score is None


def test_candidate_rejects_breakdown_larger_than_route() -> None:
    with pytest.raises(ValidationError):
        RouteCandidate(
            id=uuid4(),
            name="Invalid provider route",
            activity_kind=ActivityKind.HIKING,
            distance_meters=100,
            geometry=geometry(),
            provenance=[provenance()],
            surface_breakdown=[
                SurfaceSummary(value="paved", proportion=0.6),
                SurfaceSummary(value="unpaved", proportion=0.5),
            ],
        )


def test_candidate_validates_each_technical_characteristic_separately() -> None:
    candidate = RouteCandidate(
        id=uuid4(),
        name="Independent technical distributions",
        activity_kind=ActivityKind.HIKING,
        distance_meters=1000,
        geometry=geometry(),
        provenance=[provenance()],
        technical_breakdown=[
            TechnicalSummary(
                characteristic="grade", value="gentle", proportion=0.4
            ),
            TechnicalSummary(
                characteristic="grade", value="steep", proportion=0.6
            ),
            TechnicalSummary(
                characteristic="smoothness", value="smooth", distance_meters=250
            ),
            TechnicalSummary(
                characteristic="smoothness", value="rough", distance_meters=750
            ),
        ],
    )

    assert len(candidate.technical_breakdown) == 4


@pytest.mark.parametrize("measure", ["proportion", "distance_meters"])
def test_candidate_rejects_oversized_single_technical_distribution(
    measure: str,
) -> None:
    values = (0.6, 0.5) if measure == "proportion" else (600, 500)
    summaries = [
        TechnicalSummary(
            characteristic="grade", value="gentle", **{measure: values[0]}
        ),
        TechnicalSummary(
            characteristic="grade", value="steep", **{measure: values[1]}
        ),
        TechnicalSummary(
            characteristic="smoothness",
            value="smooth",
            **{measure: 1 if measure == "proportion" else 1000},
        ),
    ]

    with pytest.raises(ValidationError):
        RouteCandidate(
            id=uuid4(),
            name="Invalid technical distribution",
            activity_kind=ActivityKind.HIKING,
            distance_meters=1000,
            geometry=geometry(),
            provenance=[provenance()],
            technical_breakdown=summaries,
        )
