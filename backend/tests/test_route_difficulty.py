from uuid import uuid4

import pytest

from app.domain.activities import ActivityKind
from app.domain.routes import (
    GeoJsonLineString,
    ProviderProvenance,
    RouteCandidate,
    SurfaceSummary,
    TechnicalSummary,
)
from app.services.route_difficulty import (
    DIFFICULTY_SCORING_VERSION,
    UnsupportedDifficultyScoringError,
    assess_route_difficulty,
    score_route_candidate,
)


def route(
    kind: ActivityKind = ActivityKind.HIKING,
    *,
    distance: float = 10_000.0,
    elevation: float | None = 500.0,
    surfaces: list[SurfaceSummary] | None = None,
    technical: list[TechnicalSummary] | None = None,
) -> RouteCandidate:
    return RouteCandidate(
        id=uuid4(),
        name="Test route",
        activity_kind=kind,
        distance_meters=distance,
        elevation_gain_meters=elevation,
        geometry=GeoJsonLineString(coordinates=[(0.0, 0.0), (0.01, 0.01)]),
        surface_breakdown=surfaces or [],
        technical_breakdown=technical or [],
        provenance=[ProviderProvenance(provider="test", attribution="Test")],
    )


def component(assessment, name: str):
    return next(item for item in assessment.components if item.name == name)


@pytest.mark.parametrize("metric", ["distance", "elevation_gain", "climbing_density"])
def test_scalar_components_are_monotonic(metric: str) -> None:
    low = assess_route_difficulty(route(distance=10_000, elevation=200))
    if metric == "distance":
        high = assess_route_difficulty(route(distance=20_000, elevation=200))
    elif metric == "elevation_gain":
        high = assess_route_difficulty(route(distance=10_000, elevation=800))
    else:
        high = assess_route_difficulty(route(distance=5_000, elevation=200))
    assert component(high, metric).score >= component(low, metric).score


def test_surface_is_activity_specific_and_unknown_is_not_hard() -> None:
    unpaved = [SurfaceSummary(value="unpaved", proportion=1.0)]
    road = assess_route_difficulty(route(ActivityKind.ROAD_CYCLING, surfaces=unpaved))
    gravel = assess_route_difficulty(
        route(ActivityKind.GRAVEL_CYCLING, surfaces=unpaved)
    )
    assert component(road, "surface").score > component(gravel, "surface").score

    unknown = assess_route_difficulty(
        route(surfaces=[SurfaceSummary(value="unknown", proportion=1.0)])
    )
    assert component(unknown, "surface").score is None
    assert not component(unknown, "surface").evidence_available
    assert unknown.evidence_coverage < road.evidence_coverage


def test_missing_facts_reduce_coverage_without_fabricated_scores() -> None:
    only_distance = assess_route_difficulty(route(elevation=None))
    assert component(only_distance, "distance").evidence_available
    for name in (
        "elevation_gain",
        "climbing_density",
        "surface",
        "steepness",
        "trail_difficulty",
    ):
        assert component(only_distance, name).score is None
    assert only_distance.evidence_coverage == pytest.approx(0.25)
    assert only_distance.score == component(only_distance, "distance").score


def test_steepness_uses_route_share_not_only_worst_category() -> None:
    little = [
        TechnicalSummary(
            characteristic="steepness", value="extreme_decline", proportion=0.01
        ),
        TechnicalSummary(characteristic="steepness", value="level", proportion=0.99),
    ]
    much = [
        TechnicalSummary(
            characteristic="steepness", value="extreme_decline", proportion=0.5
        ),
        TechnicalSummary(characteristic="steepness", value="level", proportion=0.5),
    ]
    assert component(
        assess_route_difficulty(route(technical=little)), "steepness"
    ).score == pytest.approx(0.01)
    assert component(
        assess_route_difficulty(route(technical=much)), "steepness"
    ).score == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("kind", "easy", "hard"),
    [
        (ActivityKind.HIKING, "hiking", "difficult_alpine_hiking"),
        (ActivityKind.MOUNTAIN_BIKING, "mountain_bike_s0", "mountain_bike_s5"),
    ],
)
def test_trail_difficulty_has_activity_relevant_interpretations(
    kind, easy, hard
) -> None:
    def assessed(value):
        facts = [
            TechnicalSummary(
                characteristic="trail_difficulty", value=value, proportion=1.0
            )
        ]
        return component(
            assess_route_difficulty(route(kind, technical=facts)), "trail_difficulty"
        ).score

    assert assessed(hard) > assessed(easy)


@pytest.mark.parametrize(
    ("kind", "mismatched_label"),
    [
        (ActivityKind.HIKING, "mountain_bike_s5"),
        (ActivityKind.MOUNTAIN_BIKING, "difficult_alpine_hiking"),
    ],
)
def test_trail_difficulty_rejects_another_activity_scale(
    kind: ActivityKind, mismatched_label: str
) -> None:
    facts = [
        TechnicalSummary(
            characteristic="trail_difficulty",
            value=mismatched_label,
            proportion=1.0,
        )
    ]
    assessment = assess_route_difficulty(route(kind, technical=facts))

    assert component(assessment, "trail_difficulty").score is None
    assert "missing_trail_difficulty_evidence" in assessment.warnings


def test_partial_technical_distributions_have_specific_warnings() -> None:
    facts = [
        TechnicalSummary(
            characteristic="steepness", value="steep_incline", proportion=0.5
        ),
        TechnicalSummary(
            characteristic="trail_difficulty", value="mountain_hiking", proportion=0.5
        ),
    ]
    assessment = assess_route_difficulty(
        route(
            surfaces=[SurfaceSummary(value="ground", proportion=1.0)],
            technical=facts,
        )
    )

    assert "partial_surface_evidence" not in assessment.warnings
    assert "partial_steepness_evidence" in assessment.warnings
    assert "partial_trail_difficulty_evidence" in assessment.warnings


def test_small_unknown_distribution_share_reduces_coverage_without_warning() -> None:
    assessment = assess_route_difficulty(route(
        surfaces=[
            SurfaceSummary(value="asphalt", proportion=0.99),
            SurfaceSummary(value="unknown", proportion=0.01),
        ],
        technical=[
            TechnicalSummary(
                characteristic="steepness", value="level", proportion=0.99
            )
        ],
    ))

    assert assessment.evidence_coverage < 1
    assert "partial_surface_evidence" not in assessment.warnings
    assert "partial_steepness_evidence" not in assessment.warnings


def test_scoring_is_bounded_versioned_batch_independent_and_copying() -> None:
    candidate = route(surfaces=[SurfaceSummary(value="sand", proportion=1.0)])
    alone = assess_route_difficulty(candidate)
    _others = [
        assess_route_difficulty(route(distance=value)) for value in (1_000, 40_000)
    ]
    beside_others = assess_route_difficulty(candidate)
    assert alone == beside_others
    assert alone.scoring_version == DIFFICULTY_SCORING_VERSION
    assert 0 <= alone.score <= 1
    assert 0 <= alone.evidence_coverage <= 1
    assert all(item.score is None or 0 <= item.score <= 1 for item in alone.components)
    scored, assessment = score_route_candidate(candidate)
    assert candidate.difficulty_score is None
    assert scored.difficulty_score == assessment.score


def test_unsupported_activity_is_controlled() -> None:
    with pytest.raises(
        UnsupportedDifficultyScoringError,
        match="No difficulty-v1",
    ):
        assess_route_difficulty(route(ActivityKind.ALPINE_SKIING))
