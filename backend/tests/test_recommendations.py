from uuid import UUID

import pytest

from app.domain.activities import ActivityKind
from app.domain.planning import (
    DesiredChallenge,
    NoveltyPreference,
    RoutePlanningRequest,
)
from app.domain.planning_areas import PlanningArea
from app.domain.recommendations import NoveltyAssessment, NoveltyStatus
from app.domain.routes import (
    GeoJsonLineString,
    ProviderProvenance,
    RouteCandidate,
    RouteShape,
)
from app.services.recommendations import (
    BALANCED_NOVELTY_TARGET,
    assess_preference_alignment,
    relative_closeness,
)
from app.services.route_difficulty import assess_route_difficulty


def planning(**updates):
    return RoutePlanningRequest(
        planning_area=PlanningArea(
            latitude=49.2,
            longitude=-123.1,
            display_name="Test",
            source_provider="test",
            source_attribution="test",
        ),
        activity_kind=ActivityKind.HIKING,
        **updates,
    )


def candidate(*, distance=10_000.0, duration=3_600):
    return RouteCandidate(
        id=UUID(int=1),
        name="Candidate",
        activity_kind=ActivityKind.HIKING,
        distance_meters=distance,
        estimated_duration_seconds=duration,
        elevation_gain_meters=300.0,
        route_shape=RouteShape.LOOP,
        geometry=GeoJsonLineString(coordinates=[(-123.1, 49.2), (-123.09, 49.21)]),
        provenance=[ProviderProvenance(provider="test", attribution="test")],
    )


def novelty(value):
    available = value is not None
    return NoveltyAssessment(
        status=NoveltyStatus.AVAILABLE
        if available
        else NoveltyStatus.INSUFFICIENT_HISTORY,
        novelty_score=value,
        confidence=1 if available else 0,
        eligible_activity_count=1,
        geometry_activity_count=1 if available else 0,
        missing_geometry_activity_count=0 if available else 1,
        geometry_coverage_ratio=1 if available else 0,
    )


def alignment(route, request, value=0.5):
    return assess_preference_alignment(
        route, request, assess_route_difficulty(route), novelty(value)
    )


def component(result, name):
    return next(item for item in result.components if item.name == name)


def test_relative_target_closeness_is_symmetric_and_bounded():
    assert relative_closeness(10_000, 10_000) == 1
    assert relative_closeness(5_000, 10_000) == relative_closeness(10_000, 5_000)
    assert relative_closeness(5_000, 10_000) > relative_closeness(1_000, 10_000)


def test_distance_duration_and_shape_alignment():
    request = planning(
        target_distance_meters=10_000.0,
        target_duration_seconds=3_600,
        route_shape=RouteShape.LOOP,
    )
    exact = alignment(candidate(), request)
    assert component(exact, "target_distance").score == 1
    assert component(exact, "target_duration").score == 1
    assert component(exact, "route_shape").score == 1
    missing = alignment(candidate(duration=None), request)
    assert component(missing, "target_duration").score is None
    assert missing.evidence_coverage < 1


@pytest.mark.parametrize("challenge", list(DesiredChallenge))
def test_each_challenge_produces_explicit_alignment(challenge):
    assert (
        component(
            alignment(candidate(), planning(desired_challenge=challenge)),
            "desired_challenge",
        ).score
        is not None
    )


def test_novelty_preferences_are_distinct():
    familiar = alignment(
        candidate(), planning(novelty_preference=NoveltyPreference.FAMILIAR), 0.1
    )
    novel = alignment(
        candidate(), planning(novelty_preference=NoveltyPreference.NOVEL), 0.9
    )
    balanced = alignment(
        candidate(),
        planning(novelty_preference=NoveltyPreference.BALANCED),
        BALANCED_NOVELTY_TARGET,
    )
    assert familiar.score == pytest.approx(0.9)
    assert novel.score == pytest.approx(0.9)
    assert balanced.score == 1


def test_unknown_novelty_and_omitted_preferences():
    unknown = alignment(
        candidate(), planning(novelty_preference=NoveltyPreference.NOVEL), None
    )
    assert unknown.score is None
    assert unknown.evidence_coverage == 0
    assert "missing_novelty_preference_alignment_evidence" in unknown.warnings
    omitted = alignment(candidate(), planning())
    assert omitted.score is None
    assert omitted.components == []
    assert omitted.evidence_coverage == 1
