"""Pure v1 athlete-fit scoring from existing profile and candidate facts."""

from app.domain.athlete_profile import (
    AthleteProfile,
    ConsistencySignals,
    RepresentativeRange,
)
from app.domain.planning import DesiredChallenge, RoutePlanningRequest
from app.domain.recommendations import (
    AthleteFitAssessment,
    AthleteFitComponent,
    AthleteFitStatus,
    RouteDifficultyAssessment,
)
from app.domain.routes import RouteCandidate

ATHLETE_FIT_SCORING_VERSION = "athlete-fit-v1"

# A missing challenge means "use my profile", represented by the median.
CHALLENGE_CAPABILITY_ANCHORS: dict[DesiredChallenge | None, str] = {
    DesiredChallenge.EASY: "p25",
    DesiredChallenge.MODERATE: "median",
    DesiredChallenge.HARD: "p90",
    None: "median",
}
# Difficulty is only an auxiliary preference signal when challenge is explicit.
CHALLENGE_DIFFICULTY_TARGETS = {
    DesiredChallenge.EASY: 0.25,
    DesiredChallenge.MODERATE: 0.5,
    DesiredChallenge.HARD: 0.8,
}
COMPONENT_WEIGHTS = {
    "distance_capability": 0.35,
    "duration_capability": 0.2,
    "elevation_capability": 0.15,
    "climbing_density_capability": 0.1,
    "current_consistency": 0.15,
    "challenge_difficulty_alignment": 0.05,
}


def _summary(request: RoutePlanningRequest, profile: AthleteProfile):
    return next(
        (
            item
            for item in profile.activity_summaries
            if item.activity_kind == request.activity_kind
        ),
        None,
    )


def resolve_profile_target_distance(
    planning_request: RoutePlanningRequest, athlete_profile: AthleteProfile
) -> float | None:
    """Resolve explicit distance first, otherwise the matching profile anchor."""
    if planning_request.target_distance_meters is not None:
        return planning_request.target_distance_meters
    summary = _summary(planning_request, athlete_profile)
    if summary is None:
        return None
    anchor = CHALLENGE_CAPABILITY_ANCHORS[planning_request.desired_challenge]
    return getattr(summary.capability_ranges.distance_meters, anchor)


def _capability_score(value: float, target: float, capability_p90: float) -> float:
    """Asymmetric smooth fit: undershoot is gentle; p90 overshoot is severe.

    Values below target lose at most 35% proportionally. Above target loses 35%
    per target multiple. Beyond p90 an additional continuous penalty loses 90%
    per p90 multiple, with a 0.05 floor. There is no threshold discontinuity.
    """
    if target <= 0:
        target_alignment = 1.0 if value <= 0 else 0.05
    elif value <= target:
        target_alignment = 1 - 0.35 * (1 - value / target)
    else:
        target_alignment = max(0.1, 1 - 0.35 * (value / target - 1))
    overshoot = (
        max(0.05, 1 - 0.9 * (value / capability_p90 - 1))
        if capability_p90 > 0 and value > capability_p90
        else 1.0
    )
    return max(0.0, min(1.0, target_alignment * overshoot))


def _component(
    name: str, value: float, target: float, capability: RepresentativeRange
) -> AthleteFitComponent:
    return AthleteFitComponent(
        name=name,
        score=_capability_score(value, target, capability.p90),
        evidence=[
            f"candidate={value:.1f}",
            f"target={target:.1f}",
            f"profile_p90={capability.p90:.1f}",
            f"profile_sample_size={capability.sample_size}",
        ],
    )


def _consistency_component(
    signals: ConsistencySignals, high_end_fraction: float
) -> AthleteFitComponent:
    recency_support = max(0.0, 1 - signals.days_since_last_activity / 42)
    ratio = signals.recency.recent_to_baseline
    volume_support = (
        min(1.0, ratio.moving_time_seconds_per_week_ratio)
        if ratio and ratio.moving_time_seconds_per_week_ratio is not None
        else min(1.0, signals.recency.weekly_volume.moving_time_seconds_per_week / 3600)
    )
    raw = 0.4 * signals.active_week_ratio + 0.3 * recency_support + 0.3 * volume_support
    score = 1 - min(1.0, high_end_fraction) * (1 - raw)
    evidence = [
        f"active_week_ratio={signals.active_week_ratio:.3f}",
        f"days_since_last_activity={signals.days_since_last_activity}",
        "recent_moving_time_seconds_per_week="
        f"{signals.recency.weekly_volume.moving_time_seconds_per_week:.1f}",
    ]
    if ratio and ratio.moving_time_seconds_per_week_ratio is not None:
        evidence.append(
            "recent_to_baseline_moving_time_ratio="
            f"{ratio.moving_time_seconds_per_week_ratio:.3f}"
        )
    return AthleteFitComponent(
        name="current_consistency", score=score, evidence=evidence
    )


def assess_athlete_fit(
    candidate: RouteCandidate,
    planning_request: RoutePlanningRequest,
    athlete_profile: AthleteProfile,
    difficulty: RouteDifficultyAssessment | None = None,
) -> AthleteFitAssessment:
    """Assess candidate fit using only its explicitly requested activity history."""
    if candidate.activity_kind != planning_request.activity_kind:
        return AthleteFitAssessment(
            score=None,
            confidence=0,
            components=[],
            status=AthleteFitStatus.UNSUPPORTED_ACTIVITY,
            scoring_version=ATHLETE_FIT_SCORING_VERSION,
            warnings=["candidate_activity_does_not_match_request"],
        )
    summary = _summary(planning_request, athlete_profile)
    if summary is None:
        return AthleteFitAssessment(
            score=None,
            confidence=0,
            components=[],
            status=AthleteFitStatus.INSUFFICIENT_HISTORY,
            scoring_version=ATHLETE_FIT_SCORING_VERSION,
            warnings=["no_matching_activity_history"],
        )

    ranges = summary.capability_ranges
    anchor = CHALLENGE_CAPABILITY_ANCHORS[planning_request.desired_challenge]
    distance_target = resolve_profile_target_distance(planning_request, athlete_profile)
    assert distance_target is not None
    components = [
        _component(
            "distance_capability",
            candidate.distance_meters,
            distance_target,
            ranges.distance_meters,
        )
    ]
    used_ranges = [ranges.distance_meters]
    high_end = candidate.distance_meters / max(ranges.distance_meters.p90, 1)
    warnings: list[str] = []

    if candidate.estimated_duration_seconds is not None:
        duration_target = planning_request.target_duration_seconds or getattr(
            ranges.moving_time_seconds, anchor
        )
        components.append(
            _component(
                "duration_capability",
                candidate.estimated_duration_seconds,
                duration_target,
                ranges.moving_time_seconds,
            )
        )
        used_ranges.append(ranges.moving_time_seconds)
        high_end = max(
            high_end,
            candidate.estimated_duration_seconds
            / max(ranges.moving_time_seconds.p90, 1),
        )
    else:
        warnings.append("missing_candidate_duration")

    if candidate.elevation_gain_meters is not None and ranges.elevation_gain_meters:
        elevation_target = getattr(ranges.elevation_gain_meters, anchor)
        components.append(
            _component(
                "elevation_capability",
                candidate.elevation_gain_meters,
                elevation_target,
                ranges.elevation_gain_meters,
            )
        )
        used_ranges.append(ranges.elevation_gain_meters)
        high_end = max(
            high_end,
            candidate.elevation_gain_meters / max(ranges.elevation_gain_meters.p90, 1),
        )
        if candidate.distance_meters > 0 and ranges.elevation_gain_meters_per_km:
            density = candidate.elevation_gain_meters / (
                candidate.distance_meters / 1000
            )
            density_range = ranges.elevation_gain_meters_per_km
            components.append(
                _component(
                    "climbing_density_capability",
                    density,
                    getattr(density_range, anchor),
                    density_range,
                )
            )
            used_ranges.append(density_range)
            high_end = max(high_end, density / max(density_range.p90, 1))
    else:
        warnings.append("missing_elevation_fit_evidence")

    consistency = next(
        (
            item
            for item in athlete_profile.consistency_signals
            if item.activity_kind == candidate.activity_kind
        ),
        None,
    )
    if consistency:
        components.append(_consistency_component(consistency, high_end))
    else:
        warnings.append("missing_consistency_evidence")

    if planning_request.desired_challenge is not None:
        if difficulty is not None:
            target = CHALLENGE_DIFFICULTY_TARGETS[planning_request.desired_challenge]
            components.append(
                AthleteFitComponent(
                    name="challenge_difficulty_alignment",
                    score=max(0.0, 1 - abs(difficulty.score - target) / 0.5),
                    evidence=[
                        f"difficulty={difficulty.score:.3f}",
                        f"challenge_target={target:.3f}",
                    ],
                )
            )
        else:
            warnings.append("missing_difficulty_for_challenge_alignment")

    available_weight = sum(COMPONENT_WEIGHTS[item.name] for item in components)
    score = (
        sum(item.score * COMPONENT_WEIGHTS[item.name] for item in components)
        / available_weight
    )
    sample_confidence = sum(
        min(1.0, item.sample_size / 10) for item in used_ranges
    ) / len(used_ranges)
    capability_dimensions = sum(
        item.name.endswith("_capability") for item in components
    )
    dimension_confidence = capability_dimensions / 4
    consistency_confidence = 1.0 if consistency else 0.0
    baseline_confidence = (
        1.0
        if consistency
        and consistency.recency.recent_to_baseline
        and consistency.recency.recent_to_baseline.moving_time_seconds_per_week_ratio
        is not None
        else 0.0
    )
    confidence = (
        0.45 * sample_confidence
        + 0.3 * dimension_confidence
        + 0.15 * consistency_confidence
        + 0.1 * baseline_confidence
    )
    return AthleteFitAssessment(
        score=score,
        confidence=confidence,
        components=components,
        status=AthleteFitStatus.SCORED,
        scoring_version=ATHLETE_FIT_SCORING_VERSION,
        warnings=warnings,
    )


def score_route_candidate_fit(
    candidate: RouteCandidate,
    planning_request: RoutePlanningRequest,
    athlete_profile: AthleteProfile,
    difficulty: RouteDifficultyAssessment | None = None,
) -> tuple[RouteCandidate, AthleteFitAssessment]:
    """Copy a candidate, populating athlete fit only when it is available."""
    assessment = assess_athlete_fit(
        candidate, planning_request, athlete_profile, difficulty
    )
    return candidate.model_copy(
        update={"athlete_fit_score": assessment.score}
    ), assessment
