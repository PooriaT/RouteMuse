"""Deterministic personalized ranking followed by route diversity selection."""

from dataclasses import dataclass

from app.db.repositories.athlete_profile import AthleteProfileRepository
from app.db.repositories.strava import StravaConnectionRepository
from app.domain.calendar import calendar_period_bounds
from app.domain.history import HistoricalGeometryHistory
from app.domain.planning import (
    NoveltyPreference,
    RoutePlanningRequest,
)
from app.domain.recommendations import (
    AthleteFitAssessment,
    AthleteFitStatus,
    ExcitementAssessment,
    NoveltyAssessment,
    PreferenceAlignmentAssessment,
    RankedRecommendation,
    RecommendationConfidence,
    RecommendationRequest,
    RecommendationResult,
    RecommendationScorecard,
    RouteDifficultyAssessment,
    ScoreComponent,
)
from app.domain.routes import RouteCandidate, RouteDiscoveryRequest
from app.integrations.contracts import RouteDiscoveryProvider, RoutingProvider
from app.integrations.routing.errors import (
    RouteProviderTemporaryError,
    RouteProviderTimeoutError,
)
from app.services.athlete_fit import (
    CHALLENGE_DIFFICULTY_TARGETS,
    assess_athlete_fit,
    resolve_profile_target_distance,
)
from app.services.athlete_profile import calculate_activity_summaries
from app.services.route_candidates import (
    generate_route_candidates,
    geometries_are_similar,
)
from app.services.route_difficulty import assess_route_difficulty
from app.services.route_excitement import assess_route_excitement
from app.services.route_novelty import assess_route_novelty

FINAL_RANKING_VERSION = "recommendation-v1"
PREFERENCE_ALIGNMENT_VERSION = "preference-alignment-v1"
RECOMMENDATION_CONFIDENCE_VERSION = "recommendation-confidence-v1"
RECOMMENDATION_COUNT = 3
FINAL_DIVERSITY_SIMILARITY_THRESHOLD = 0.60

# Product heuristics, not scientifically optimized weights. Missing optional
# components are omitted and these weights are renormalized.
FINAL_RANKING_WEIGHTS = {
    "athlete_fit": 0.40,
    "preference_alignment": 0.30,
    "excitement": 0.20,
    "confidence": 0.10,
}
PREFERENCE_WEIGHTS = {
    "target_distance": 0.30,
    "target_duration": 0.20,
    "desired_challenge": 0.20,
    "route_shape": 0.10,
    "novelty_preference": 0.20,
}
CONFIDENCE_WEIGHTS = {
    "candidate_data": 0.20,
    "athlete_fit": 0.30,
    "novelty_history": 0.15,
    "excitement_evidence": 0.20,
    "difficulty_evidence": 0.15,
}
BALANCED_NOVELTY_TARGET = 0.50
CHALLENGE_ALIGNMENT_TOLERANCE = 0.50


class RecommendationError(Exception):
    """Controlled orchestration failure with a stable API code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def relative_closeness(actual: float, target: float) -> float:
    """Symmetric bounded closeness using relative rather than absolute error."""
    return max(0.0, 1.0 - abs(actual - target) / max(actual, target))


def assess_preference_alignment(
    candidate: RouteCandidate,
    request: RoutePlanningRequest,
    difficulty: RouteDifficultyAssessment,
    novelty: NoveltyAssessment,
) -> PreferenceAlignmentAssessment:
    components: list[ScoreComponent] = []
    warnings: list[str] = []

    def add(name: str, score: float | None, summary: str) -> None:
        available = score is not None
        components.append(
            ScoreComponent(
                name=name,
                score=score,
                weight=PREFERENCE_WEIGHTS[name],
                evidence_available=available,
                evidence_summary=summary,
            )
        )
        if not available:
            warnings.append(f"missing_{name}_alignment_evidence")

    if request.target_distance_meters is not None:
        add(
            "target_distance",
            relative_closeness(
                candidate.distance_meters, request.target_distance_meters
            ),
            f"candidate={candidate.distance_meters:.1f}, "
            f"target={request.target_distance_meters:.1f}",
        )
    if request.target_duration_seconds is not None:
        duration = candidate.estimated_duration_seconds
        add(
            "target_duration",
            relative_closeness(duration, request.target_duration_seconds)
            if duration is not None
            else None,
            f"candidate={duration}, target={request.target_duration_seconds}",
        )
    if request.desired_challenge is not None:
        target = CHALLENGE_DIFFICULTY_TARGETS[request.desired_challenge]
        add(
            "desired_challenge",
            max(
                0.0,
                1.0 - abs(difficulty.score - target) / CHALLENGE_ALIGNMENT_TOLERANCE,
            ),
            f"difficulty={difficulty.score:.3f}, target={target:.3f}",
        )
    if request.route_shape is not None:
        add(
            "route_shape",
            1.0 if candidate.route_shape == request.route_shape else 0.0,
            f"candidate={candidate.route_shape}, requested={request.route_shape.value}",
        )
    if request.novelty_preference is not None:
        value = novelty.novelty_score
        if value is None:
            alignment = None
        elif request.novelty_preference is NoveltyPreference.NOVEL:
            alignment = value
        elif request.novelty_preference is NoveltyPreference.FAMILIAR:
            alignment = 1.0 - value
        else:
            alignment = max(0.0, 1.0 - abs(value - BALANCED_NOVELTY_TARGET) / 0.5)
        add(
            "novelty_preference",
            alignment,
            f"novelty={value}, preference={request.novelty_preference.value}",
        )

    available = [item for item in components if item.score is not None]
    available_weight = sum(item.weight for item in available)
    requested_weight = sum(item.weight for item in components)
    score = (
        sum(item.score * item.weight for item in available if item.score is not None)
        / available_weight
        if available_weight
        else None
    )
    coverage = available_weight / requested_weight if requested_weight else 1.0
    return PreferenceAlignmentAssessment(
        score=score,
        components=components,
        evidence_coverage=coverage,
        scoring_version=PREFERENCE_ALIGNMENT_VERSION,
        warnings=warnings,
    )


def assess_recommendation_confidence(
    candidate: RouteCandidate,
    fit: AthleteFitAssessment,
    novelty: NoveltyAssessment,
    excitement: ExcitementAssessment,
    difficulty: RouteDifficultyAssessment,
) -> RecommendationConfidence:
    values = {
        "candidate_data": candidate.data_confidence,
        "athlete_fit": fit.confidence,
        "novelty_history": novelty.confidence,
        "excitement_evidence": excitement.evidence_coverage,
        "difficulty_evidence": difficulty.evidence_coverage,
    }
    components = [
        ScoreComponent(
            name=name,
            score=value,
            weight=CONFIDENCE_WEIGHTS[name],
            evidence_available=value is not None,
            evidence_summary=f"{name}={value}"
            if value is not None
            else f"{name} unknown",
        )
        for name, value in values.items()
    ]
    available = [item for item in components if item.score is not None]
    weight = sum(item.weight for item in available)
    score = (
        sum(item.score * item.weight for item in available if item.score is not None)
        / weight
    )
    return RecommendationConfidence(
        score=score,
        components=components,
        scoring_version=RECOMMENDATION_CONFIDENCE_VERSION,
    )


@dataclass(frozen=True)
class _Scored:
    candidate: RouteCandidate
    scorecard: RecommendationScorecard
    warnings: list[str]


def score_recommendation(
    candidate: RouteCandidate,
    planning_request: RoutePlanningRequest,
    athlete_profile,
    history: HistoricalGeometryHistory,
    trail_features,
) -> _Scored | None:
    difficulty = assess_route_difficulty(candidate)
    fit = assess_athlete_fit(candidate, planning_request, athlete_profile, difficulty)
    # Controlled strategy: exclude candidates without matching personalized fit.
    if fit.status is not AthleteFitStatus.SCORED or fit.score is None:
        return None
    novelty = assess_route_novelty(candidate.geometry, history)
    excitement = assess_route_excitement(candidate, novelty, trail_features)
    preferences = assess_preference_alignment(
        candidate, planning_request, difficulty, novelty
    )
    confidence = assess_recommendation_confidence(
        candidate, fit, novelty, excitement, difficulty
    )
    values = {
        "athlete_fit": fit.score,
        "preference_alignment": preferences.score,
        "excitement": excitement.score,
        "confidence": confidence.score,
    }
    available = {name: value for name, value in values.items() if value is not None}
    total_weight = sum(FINAL_RANKING_WEIGHTS[name] for name in available)
    final = (
        sum(value * FINAL_RANKING_WEIGHTS[name] for name, value in available.items())
        / total_weight
    )
    scored_candidate = candidate.model_copy(
        update={
            "difficulty_score": difficulty.score,
            "athlete_fit_score": fit.score,
            "novelty_score": novelty.novelty_score,
            "excitement_score": excitement.score,
            "confidence_score": confidence.score,
        }
    )
    scorecard = RecommendationScorecard(
        final_score=final,
        ranking_version=FINAL_RANKING_VERSION,
        difficulty=difficulty,
        athlete_fit=fit,
        novelty=novelty,
        excitement=excitement,
        preference_alignment=preferences,
        confidence=confidence,
    )
    return _Scored(
        scored_candidate,
        scorecard,
        [
            *candidate.warnings,
            *difficulty.warnings,
            *fit.warnings,
            *excitement.warnings,
            *preferences.warnings,
        ],
    )


def rank_and_select(
    scored: list[_Scored], limit: int = RECOMMENDATION_COUNT
) -> list[RankedRecommendation]:
    ordered = sorted(
        scored,
        key=lambda item: (
            -item.scorecard.final_score,
            -float(item.scorecard.athlete_fit.score or 0),
            str(item.candidate.id),
        ),
    )
    selected: list[_Scored] = []
    for item in ordered:
        if not any(
            geometries_are_similar(
                item.candidate.geometry,
                existing.candidate.geometry,
                threshold=FINAL_DIVERSITY_SIMILARITY_THRESHOLD,
            )
            for existing in selected
        ):
            selected.append(item)
        if len(selected) == limit:
            break
    return [
        RankedRecommendation(
            rank=index,
            candidate=item.candidate,
            final_score=item.scorecard.final_score,
            difficulty=item.scorecard.difficulty,
            athlete_fit=item.scorecard.athlete_fit,
            novelty=item.scorecard.novelty,
            excitement=item.scorecard.excitement,
            preference_alignment=item.scorecard.preference_alignment,
            confidence=item.scorecard.confidence,
            scorecard=item.scorecard,
            warnings=item.warnings,
        )
        for index, item in enumerate(selected, 1)
    ]


async def build_recommendations(
    request: RecommendationRequest,
    profile_repository: AthleteProfileRepository,
    geometry_repository: StravaConnectionRepository,
    routing_provider: RoutingProvider,
    discovery_provider: RouteDiscoveryProvider,
) -> RecommendationResult:
    bounds = calendar_period_bounds(
        request.start_date, request.end_date, request.timezone
    )
    persisted = profile_repository.load_current_history(
        start_at=bounds.start_at, end_at_exclusive=bounds.end_at_exclusive
    )
    if persisted is None:
        raise RecommendationError(
            "strava_connection_required",
            "Connect Strava before requesting recommendations.",
        )
    if persisted.has_incomplete_synchronization:
        raise RecommendationError(
            "athlete_profile_history_incomplete",
            "Complete the interrupted activity import first.",
        )
    profile = calculate_activity_summaries(
        persisted.activities,
        period_start=request.start_date,
        period_end=request.end_date,
        timezone=request.timezone,
    )
    target = resolve_profile_target_distance(request.planning_request, profile)
    if target is None:
        raise RecommendationError(
            "recommendation_target_unavailable",
            "No explicit target or matching athlete history can resolve a distance.",
        )
    resolved = request.planning_request.model_copy(
        update={"target_distance_meters": target}
    )
    generated = await generate_route_candidates(resolved, routing_provider)
    history = geometry_repository.load_historical_geometries(
        started_at=bounds.start_at, ended_at_exclusive=bounds.end_at_exclusive
    )
    warnings = list(generated.warnings)
    try:
        trail_features = await discovery_provider.discover(
            RouteDiscoveryRequest(
                planning_area=resolved.planning_area,
                activity_kind=resolved.activity_kind,
                search_radius_meters=min(25_000.0, max(1_000.0, target / 2)),
            )
        )
    except (RouteProviderTimeoutError, RouteProviderTemporaryError):
        trail_features = None
        warnings.append("trail_discovery_unavailable")
    scored = [
        item
        for candidate in generated.candidates
        if (
            item := score_recommendation(
                candidate, request.planning_request, profile, history, trail_features
            )
        )
        is not None
    ]
    if not scored:
        raise RecommendationError(
            "personalized_recommendations_unavailable",
            "No candidate has matching athlete-fit evidence.",
        )
    recommendations = rank_and_select(scored)
    if len(recommendations) < min(RECOMMENDATION_COUNT, len(scored)):
        warnings.append("fewer_diverse_recommendations_available")
    return RecommendationResult(
        recommendations=recommendations,
        requested_recommendations=RECOMMENDATION_COUNT,
        generated_candidates=len(generated.candidates),
        ranking_version=FINAL_RANKING_VERSION,
        warnings=warnings,
    )
