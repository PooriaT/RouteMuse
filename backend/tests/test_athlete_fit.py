from datetime import date
from uuid import uuid4

import pytest

from app.domain.activities import ActivityKind
from app.domain.athlete_profile import (
    ActivityCapabilityRanges,
    ActivityKindSummary,
    ActivityVolume,
    AthleteProfile,
    ConsistencySignals,
    RecencySignals,
    RepresentativeRange,
    WeeklyActivityVolume,
)
from app.domain.planning import DesiredChallenge, RoutePlanningRequest
from app.domain.planning_areas import PlanningArea
from app.domain.recommendations import AthleteFitStatus
from app.domain.routes import GeoJsonLineString, ProviderProvenance, RouteCandidate
from app.services.athlete_fit import (
    assess_athlete_fit,
    resolve_profile_target_distance,
    score_route_candidate_fit,
)


def rr(p25: float, median: float, p75: float, p90: float, samples: int = 12):
    return RepresentativeRange(
        sample_size=samples, p25=p25, median=median, p75=p75, p90=p90
    )


def profile(kind=ActivityKind.HIKING, *, samples=12, elevation=True, inactive=False):
    distance = rr(8_000, 12_000, 16_000, 20_000, samples)
    duration = rr(3_000, 5_000, 7_000, 9_000, samples)
    elevation_range = rr(200, 400, 600, 800, samples) if elevation else None
    summary = ActivityKindSummary(
        activity_kind=kind,
        activity_count=samples,
        total_distance_meters=100_000,
        total_moving_time_seconds=50_000,
        active_weeks=8,
        median_distance_meters=12_000,
        median_moving_time_seconds=5_000,
        elevation_sample_count=samples if elevation else 0,
        capability_ranges=ActivityCapabilityRanges(
            distance_meters=distance,
            moving_time_seconds=duration,
            elevation_gain_meters=elevation_range,
            elevation_gain_meters_per_km=rr(20, 35, 45, 60, samples)
            if elevation
            else None,
        ),
    )
    consistency = ConsistencySignals(
        activity_kind=kind,
        calendar_weeks=12,
        active_week_ratio=0.1 if inactive else 0.8,
        activities_per_week=1,
        longest_inactivity_gap_days=40 if inactive else 6,
        days_since_last_activity=42 if inactive else 2,
        recency=RecencySignals(
            nominal_window_days=28,
            effective_window_days=28,
            window_start=date(2026, 7, 1),
            window_end=date(2026, 7, 28),
            volume=ActivityVolume(
                activity_count=0 if inactive else 5,
                moving_time_seconds=0 if inactive else 10_000,
                distance_meters=0 if inactive else 30_000,
                active_weeks=0 if inactive else 4,
            ),
            weekly_volume=WeeklyActivityVolume(
                activities_per_week=0 if inactive else 1.25,
                moving_time_seconds_per_week=0 if inactive else 2_500,
                distance_meters_per_week=0 if inactive else 7_500,
            ),
        ),
    )
    return AthleteProfile(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 7, 28),
        timezone="UTC",
        activities_analyzed=samples,
        activity_summaries=[summary],
        consistency_signals=[consistency],
    )


def request(kind=ActivityKind.HIKING, **kwargs):
    return RoutePlanningRequest(
        planning_area=PlanningArea(
            latitude=1.0,
            longitude=1.0,
            display_name="Somewhere",
            source_provider="test",
            source_attribution="test",
        ),
        activity_kind=kind,
        **kwargs,
    )


def route(
    distance=12_000.0, *, duration=5_000, elevation=400.0, kind=ActivityKind.HIKING
):
    return RouteCandidate(
        id=uuid4(),
        name="candidate",
        activity_kind=kind,
        distance_meters=distance,
        estimated_duration_seconds=duration,
        elevation_gain_meters=elevation,
        geometry=GeoJsonLineString(coordinates=[(0.0, 0.0), (0.1, 0.1)]),
        provenance=[ProviderProvenance(provider="test", attribution="test")],
    )


def component(assessment, name):
    return next(item for item in assessment.components if item.name == name)


def test_exact_target_and_moderate_undershoot_fit_strongly() -> None:
    exact = assess_athlete_fit(
        route(12_000), request(target_distance_meters=12_000.0), profile()
    )
    under = assess_athlete_fit(
        route(10_000), request(target_distance_meters=12_000.0), profile()
    )
    assert component(exact, "distance_capability").score == 1
    assert component(under, "distance_capability").score > 0.9


def test_extreme_p90_overshoot_is_strongly_penalized() -> None:
    assessed = assess_athlete_fit(route(50_000), request(), profile())
    assert component(assessed, "distance_capability").score < 0.1


@pytest.mark.parametrize(
    ("challenge", "target"),
    [
        (DesiredChallenge.EASY, 8_000),
        (DesiredChallenge.MODERATE, 12_000),
        (DesiredChallenge.HARD, 20_000),
        (None, 12_000),
    ],
)
def test_challenge_mapping(challenge, target) -> None:
    assert (
        resolve_profile_target_distance(request(desired_challenge=challenge), profile())
        == target
    )


def test_explicit_distance_and_duration_override_profile_targets() -> None:
    planning = request(
        target_distance_meters=9_000.0,
        target_duration_seconds=4_000,
        desired_challenge=DesiredChallenge.HARD,
    )
    assessed = assess_athlete_fit(route(9_000, duration=4_000), planning, profile())
    assert component(assessed, "distance_capability").score == 1
    assert component(assessed, "duration_capability").score == 1


def test_activity_isolation_and_no_matching_history_are_unavailable() -> None:
    assessed = assess_athlete_fit(
        route(), request(), profile(ActivityKind.ROAD_CYCLING)
    )
    assert assessed.status == AthleteFitStatus.INSUFFICIENT_HISTORY
    assert assessed.score is None
    assert assessed.confidence == 0


def test_sparse_history_lowers_confidence() -> None:
    sparse = assess_athlete_fit(route(), request(), profile(samples=2))
    established = assess_athlete_fit(route(), request(), profile(samples=12))
    assert sparse.confidence < established.confidence


def test_missing_elevation_and_duration_omit_components() -> None:
    assessed = assess_athlete_fit(
        route(duration=None, elevation=None), request(), profile(elevation=False)
    )
    names = {item.name for item in assessed.components}
    assert "duration_capability" not in names
    assert "elevation_capability" not in names
    assert (
        assessed.confidence
        < assess_athlete_fit(route(), request(), profile()).confidence
    )


def test_inactivity_only_reduces_separate_consistency_support() -> None:
    active = assess_athlete_fit(route(19_000), request(), profile())
    inactive = assess_athlete_fit(route(19_000), request(), profile(inactive=True))
    assert component(active, "distance_capability") == component(
        inactive, "distance_capability"
    )
    assert (
        component(inactive, "current_consistency").score
        < component(active, "current_consistency").score
    )


def test_deterministic_and_candidate_population_does_not_set_confidence() -> None:
    candidate = route()
    first = assess_athlete_fit(candidate, request(), profile())
    second = assess_athlete_fit(candidate, request(), profile())
    assert first == second
    scored, assessment = score_route_candidate_fit(candidate, request(), profile())
    assert scored.athlete_fit_score == assessment.score
    assert scored.confidence_score is None
    assert candidate.athlete_fit_score is None
