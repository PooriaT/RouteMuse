from uuid import uuid4

import pytest

from app.domain.activities import ActivityKind
from app.domain.history import HistoricalGeometryHistory
from app.domain.routes import (
    GeoJsonLineString,
    NamedRouteReference,
    ProviderProvenance,
    RouteCandidate,
    RouteShape,
    SurfaceSummary,
    TechnicalSummary,
    TrailFeature,
    WayTypeSummary,
)
from app.services.route_excitement import (
    MINIMUM_EVIDENCE_COVERAGE,
    assess_route_excitement,
    distribution_variety,
    overlapping_named_features,
    score_candidate_excitement,
)
from app.services.route_novelty import (
    NoveltyAssessment,
    NoveltyStatus,
    assess_route_novelty,
)


def line(offset: float = 0) -> GeoJsonLineString:
    return GeoJsonLineString(
        coordinates=[(-123.1 + offset, 49.2), (-123.09 + offset, 49.2)]
    )


def candidate(**updates: object) -> RouteCandidate:
    values = dict(
        id=uuid4(),
        name="candidate",
        activity_kind=ActivityKind.HIKING,
        distance_meters=1000.0,
        geometry=line(),
        provenance=[ProviderProvenance(provider="test", attribution="test")],
    )
    values.update(updates)
    return RouteCandidate(**values)


def feature(
    *, offset: float = 0, name: str | None = "Trail", relation: bool = False
) -> TrailFeature:
    return TrailFeature(
        provider_feature_id=str(uuid4()),
        name=name,
        geometry=line(offset),
        activity_kinds=[ActivityKind.HIKING],
        named_route_memberships=(
            [NamedRouteReference(source_id="relation-1", name="Route")]
            if relation
            else []
        ),
        provenance=[ProviderProvenance(provider="test", attribution="test")],
    )


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        ([SurfaceSummary(value="paved", proportion=1.0)], 0.0),
        (
            [
                SurfaceSummary(value="paved", proportion=0.5),
                SurfaceSummary(value="gravel", proportion=0.5),
            ],
            0.5,
        ),
    ],
)
def test_surface_variety(entries, expected: float) -> None:
    score, _ = distribution_variety(entries, 1000)
    assert score == pytest.approx(expected)


def test_tiny_category_and_unknown_do_not_artificially_maximize_variety() -> None:
    dominant, coverage = distribution_variety(
        [
            SurfaceSummary(value="paved", proportion=0.99),
            SurfaceSummary(value="gravel", proportion=0.01),
            SurfaceSummary(value="unknown", distance_meters=200),
        ],
        1000,
    )
    assert dominant is not None and dominant < 0.1
    assert coverage == 1
    assert distribution_variety(
        [SurfaceSummary(value="unknown", proportion=1.0)], 1000
    ) == (None, 0)


@pytest.mark.parametrize("unknown_value", ["unknown_999", "unrated"])
def test_provider_unknown_categories_are_not_variety_evidence(
    unknown_value: str,
) -> None:
    mixed_score, mixed_coverage = distribution_variety(
        [
            SurfaceSummary(value="paved", proportion=0.5),
            SurfaceSummary(value=unknown_value, proportion=0.5),
        ],
        1000,
    )
    assert mixed_score == 0
    assert mixed_coverage == 0.5
    assert distribution_variety(
        [SurfaceSummary(value=unknown_value, proportion=1.0)], 1000
    ) == (None, 0)


def test_way_and_terrain_variety_are_proportion_aware() -> None:
    one_way = [WayTypeSummary(value="path", proportion=1.0)]
    two_ways = [
        WayTypeSummary(value="path", proportion=0.5),
        WayTypeSummary(value="track", proportion=0.5),
    ]
    assert distribution_variety(one_way, 1000)[0] == 0
    assert distribution_variety(two_ways, 1000)[0] == pytest.approx(0.5)
    varied = candidate(
        technical_breakdown=[
            TechnicalSummary(characteristic="steepness", value="level", proportion=0.5),
            TechnicalSummary(
                characteristic="steepness", value="incline", proportion=0.5
            ),
        ]
    )
    flat = candidate(
        technical_breakdown=[
            TechnicalSummary(characteristic="steepness", value="level", proportion=1.0)
        ]
    )
    assert assess_route_excitement(varied, trail_features=[]).components[3].score == 0.5
    assert assess_route_excitement(flat, trail_features=[]).components[3].score == 0


def test_named_content_requires_material_geometry_overlap() -> None:
    route = candidate()
    overlap = overlapping_named_features(
        route,
        [
            feature(),
            feature(relation=True),
            feature(offset=0.1),
            feature(name=None),
        ],
    )
    assert overlap.overlapping_named_feature_count == 1
    assert overlap.overlapping_named_route_count == 1
    assert len(overlap.features) == 2
    assert overlap.approximate_named_route_coverage > 0.9


def test_missing_evidence_lowers_coverage_and_enforces_threshold() -> None:
    assessment = assess_route_excitement(candidate())
    assert assessment.score is None
    assert assessment.evidence_coverage < MINIMUM_EVIDENCE_COVERAGE
    assert "missing_novelty_evidence" in assessment.warnings
    assert "missing_named_content_evidence" in assessment.warnings
    assert "insufficient_excitement_evidence" in assessment.warnings


def test_no_overpass_context_is_unavailable_but_empty_context_is_factual_zero() -> None:
    route = candidate(route_shape=RouteShape.LOOP)
    missing = assess_route_excitement(route)
    empty = assess_route_excitement(route, trail_features=[])
    assert missing.components[4].score is None
    assert empty.components[4].score == 0
    assert empty.evidence_coverage > missing.evidence_coverage


def test_novelty_changes_only_its_component_and_scoring_is_deterministic() -> None:
    route = candidate(
        route_shape=RouteShape.LOOP,
        surface_breakdown=[SurfaceSummary(value="ground", proportion=1.0)],
    )
    familiar = assess_route_novelty(
        route.geometry,
        HistoricalGeometryHistory(eligible_activity_count=1, geometries=[]),
    )
    novel_history = HistoricalGeometryHistory(eligible_activity_count=0, geometries=[])
    unavailable = assess_route_novelty(route.geometry, novel_history)
    assert familiar.novelty_score is None
    first = assess_route_excitement(route, unavailable, [])
    assert first == assess_route_excitement(route, unavailable, [])


def test_higher_available_novelty_raises_novelty_component() -> None:
    route = candidate(route_shape=RouteShape.LOOP)
    common = dict(
        status=NoveltyStatus.AVAILABLE,
        confidence=1,
        eligible_activity_count=10,
        geometry_activity_count=10,
        missing_geometry_activity_count=0,
        geometry_coverage_ratio=1,
    )
    identical = NoveltyAssessment(novelty_score=0.1, **common)
    distinct = NoveltyAssessment(novelty_score=0.9, **common)
    low = assess_route_excitement(route, identical, [])
    high = assess_route_excitement(route, distinct, [])
    assert high.components[0].score > low.components[0].score


def test_difficulty_is_independent_and_only_excitement_is_populated() -> None:
    route = candidate(
        difficulty_score=0.1,
        route_shape=RouteShape.LOOP,
        surface_breakdown=[SurfaceSummary(value="ground", proportion=1.0)],
    )
    changed = route.model_copy(update={"difficulty_score": 0.9})
    assert assess_route_excitement(route, trail_features=[]) == assess_route_excitement(
        changed, trail_features=[]
    )
    scored, assessment = score_candidate_excitement(route, trail_features=[])
    assert scored.excitement_score == assessment.score
    assert scored.difficulty_score == 0.1
    assert scored.confidence_score is None
