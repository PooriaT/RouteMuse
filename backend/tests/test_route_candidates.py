import asyncio
from uuid import uuid4

import pytest

from app.domain.activities import ActivityKind
from app.domain.planning import RoutePlanningRequest
from app.domain.planning_areas import PlanningArea
from app.domain.routes import (
    GeoJsonLineString,
    ProviderProvenance,
    RouteCandidate,
    RouteShape,
)
from app.integrations.routing.errors import (
    NoRouteFoundError,
    ProviderAuthenticationError,
    RouteProviderMalformedResponseError,
    RouteProviderRateLimitError,
)
from app.services.route_candidates import (
    DESIRED_CANDIDATES,
    GENERATION_ALGORITHM_VERSION,
    MAX_ATTEMPTS,
    ROUTE_SIMILARITY_THRESHOLD,
    CandidateGenerationError,
    deterministic_seeds,
    effective_target_distances,
    generate_route_candidates,
    geometries_are_similar,
)


def planning_request(
    *,
    kind: ActivityKind = ActivityKind.HIKING,
    latitude: float = 49.2,
    distance: float | None = 10_000.0,
    shape: RouteShape | None = None,
) -> RoutePlanningRequest:
    return RoutePlanningRequest(
        planning_area=PlanningArea(
            latitude=latitude,
            longitude=-123.1,
            display_name="Test area",
            source_provider="test",
            source_attribution="Test data",
        ),
        activity_kind=kind,
        target_distance_meters=distance,
        route_shape=shape,
    )


def loop(offset: float = 0.0, jitter: float = 0.0) -> GeoJsonLineString:
    return GeoJsonLineString(
        coordinates=[
            [-123.1 + offset + jitter, 49.2 + jitter],
            [-123.09 + offset + jitter, 49.2 + jitter],
            [-123.09 + offset + jitter, 49.21 + jitter],
            [-123.1 + offset + jitter, 49.21 + jitter],
            [-123.1 + offset + jitter, 49.2 + jitter],
        ]
    )


def candidate(geometry: GeoJsonLineString, *, scored: bool = False) -> RouteCandidate:
    return RouteCandidate(
        id=uuid4(),
        name="Factual provider route",
        activity_kind=ActivityKind.HIKING,
        distance_meters=10_123.0,
        geometry=geometry,
        route_shape=RouteShape.LOOP,
        provenance=[ProviderProvenance(provider="test", attribution="Test data")],
        difficulty_score=0.8 if scored else None,
    )


class FakeProvider:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.requests = []

    async def route(self, request):
        self.requests.append(request)
        outcome = self.outcomes[len(self.requests) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def run(request: RoutePlanningRequest, provider: FakeProvider):
    return asyncio.run(generate_route_candidates(request, provider))


def test_seed_sequence_is_stable_and_canonical_inputs_change_it() -> None:
    request = planning_request()
    assert deterministic_seeds(request, 8) == deterministic_seeds(request, 8)
    assert deterministic_seeds(request, 2) == [3345787845, 1295896213]
    assert deterministic_seeds(
        planning_request(kind=ActivityKind.WALKING), 8
    ) != deterministic_seeds(request, 8)
    assert deterministic_seeds(
        planning_request(latitude=49.3), 8
    ) != deterministic_seeds(request, 8)
    assert deterministic_seeds(
        planning_request(distance=11_000.0), 8
    ) != deterministic_seeds(request, 8)


def test_target_variations_are_positive_deterministic_and_documented() -> None:
    assert effective_target_distances(10_000.0, 8) == [
        10_000.0,
        9_000.0,
        11_000.0,
        9_500.0,
        10_500.0,
        10_000.0,
        9_000.0,
        11_000.0,
    ]
    assert all(value > 0 for value in effective_target_distances(0.1, 8))


def test_geometry_similarity_tolerates_direction_and_small_changes() -> None:
    original = loop()
    reversed_loop = GeoJsonLineString(coordinates=list(reversed(original.coordinates)))
    assert geometries_are_similar(original, original)
    assert geometries_are_similar(original, reversed_loop)
    assert geometries_are_similar(original, loop(jitter=0.00001))
    assert not geometries_are_similar(original, loop(offset=0.03))
    assert ROUTE_SIMILARITY_THRESHOLD == 0.8


def test_generates_desired_ordered_distinct_candidates_with_provenance() -> None:
    provider = FakeProvider(
        [candidate(loop(offset=index * 0.03), scored=True) for index in range(4)]
    )
    result = run(planning_request(), provider)
    assert len(result.candidates) == DESIRED_CANDIDATES == 4
    assert result.attempts_made == 4
    assert result.warnings == []
    for index, route in enumerate(result.candidates):
        generation = route.generation_provenance
        assert generation is not None
        assert generation.algorithm_version == GENERATION_ALGORITHM_VERSION
        assert generation.requested_distance_meters == 10_000.0
        assert (
            generation.effective_target_distance_meters
            == provider.requests[index].round_trip.target_distance_meters
        )
        assert generation.seed == provider.requests[index].round_trip.seed
        assert generation.round_trip_points == 4
        assert generation.attempt_index == index
        assert route.provenance[0].attribution == "Test data"
        assert route.difficulty_score is None
        assert route.athlete_fit_score is None
        assert route.excitement_score is None
        assert route.novelty_score is None


def test_no_route_and_duplicate_are_replaced_sequentially() -> None:
    distinct = [candidate(loop(offset=index * 0.03)) for index in range(4)]
    provider = FakeProvider(
        [
            NoRouteFoundError(),
            distinct[0],
            candidate(loop(jitter=0.00001)),
            distinct[1],
            distinct[2],
            distinct[3],
        ]
    )
    result = run(planning_request(), provider)
    assert len(result.candidates) == 4
    assert len(provider.requests) == result.attempts_made == 6
    assert [item.generation_provenance.attempt_index for item in result.candidates] == [
        1,
        3,
        4,
        5,
    ]


def test_attempt_limit_returns_partial_and_zero_is_controlled() -> None:
    duplicate = candidate(loop())
    partial_provider = FakeProvider(
        [duplicate] + [candidate(loop(jitter=0.00001)) for _ in range(7)]
    )
    result = run(planning_request(), partial_provider)
    assert len(partial_provider.requests) == MAX_ATTEMPTS == 8
    assert len(result.candidates) == 1
    assert result.warnings == ["fewer_candidates_than_desired"]

    empty_provider = FakeProvider([NoRouteFoundError() for _ in range(8)])
    with pytest.raises(CandidateGenerationError, match="No route candidates") as exc:
        run(planning_request(), empty_provider)
    assert exc.value.code == "no_route_candidates"
    assert len(empty_provider.requests) == 8


@pytest.mark.parametrize(
    "error",
    [
        RouteProviderRateLimitError(),
        ProviderAuthenticationError(),
        RouteProviderMalformedResponseError(),
    ],
)
def test_non_no_route_provider_failures_stop_immediately(error: Exception) -> None:
    provider = FakeProvider([error, candidate(loop())])
    with pytest.raises(type(error)):
        run(planning_request(), provider)
    assert len(provider.requests) == 1


def test_missing_distance_and_explicit_non_loop_shapes_are_rejected_without_calls() -> (
    None
):
    provider = FakeProvider([])
    with pytest.raises(CandidateGenerationError) as missing:
        run(planning_request(distance=None), provider)
    assert missing.value.code == "route_target_distance_required"
    for shape in (RouteShape.OUT_AND_BACK, RouteShape.POINT_TO_POINT):
        with pytest.raises(CandidateGenerationError) as unsupported:
            run(planning_request(shape=shape), provider)
        assert unsupported.value.code == "unsupported_generation_mode"
    assert provider.requests == []


def test_provider_limit_skips_attempts_and_reports_partial_or_no_result() -> None:
    provider = FakeProvider(
        [candidate(loop(offset=index * 0.03)) for index in range(8)]
    )
    result = run(planning_request(distance=100_000.0), provider)
    assert "target_variants_exceeded_provider_limit" in result.warnings
    assert all(
        request.round_trip.target_distance_meters <= 100_000
        for request in provider.requests
    )

    with pytest.raises(CandidateGenerationError) as exc:
        run(planning_request(distance=200_000.0), FakeProvider([]))
    assert exc.value.code == "route_target_exceeds_provider_limit"
