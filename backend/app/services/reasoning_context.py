"""Pure construction of the bounded recommendation reasoning projection."""

from app.domain.athlete_profile import AthleteProfile, RepresentativeRange
from app.domain.planning import RoutePlanningRequest
from app.domain.reasoning_context import (
    MAX_BREAKDOWN_ENTRIES,
    MAX_CONTEXT_STRING_LENGTH,
    MAX_REASONING_CONTEXT_CHARACTERS,
    MAX_SCORE_COMPONENTS,
    MAX_TECHNICAL_ENTRIES,
    MAX_WARNINGS,
    AthleteConsistencyContext,
    AthleteContext,
    BreakdownContext,
    EvidenceLimitationsContext,
    NoveltyContext,
    PercentileRangeContext,
    PlanningPreferencesContext,
    ProvenanceContext,
    RankedRecommendationContext,
    ReasoningContextConstructionError,
    RecommendationReasoningContext,
    RouteFactsContext,
    ScorecardContext,
    ScoreComponentContext,
    TechnicalBreakdownContext,
)
from app.domain.recommendations import RankedRecommendation

_CLIP_MARKER = "…[truncated]"


def build_reasoning_context(
    ranked_recommendation: RankedRecommendation,
    planning_request: RoutePlanningRequest,
    athlete_profile: AthleteProfile,
) -> RecommendationReasoningContext:
    """Project existing facts without scoring, I/O, geometry, or provider payloads."""
    clipped = False
    collections_truncated = False

    def clip(value: str) -> str:
        nonlocal clipped
        value = value.strip() or "unknown"
        if len(value) <= MAX_CONTEXT_STRING_LENGTH:
            return value
        clipped = True
        return value[: MAX_CONTEXT_STRING_LENGTH - len(_CLIP_MARKER)] + _CLIP_MARKER

    def bounded(items, maximum):
        nonlocal collections_truncated
        result = list(items)
        collections_truncated |= len(result) > maximum
        return result[:maximum]

    candidate = ranked_recommendation.candidate
    scorecard = ranked_recommendation.scorecard
    summary = next(
        (
            s
            for s in athlete_profile.activity_summaries
            if s.activity_kind == planning_request.activity_kind
        ),
        None,
    )
    consistency = next(
        (
            s
            for s in athlete_profile.consistency_signals
            if s.activity_kind == planning_request.activity_kind
        ),
        None,
    )

    def percentile(value: RepresentativeRange | None) -> PercentileRangeContext | None:
        return (
            PercentileRangeContext.model_validate(value.model_dump()) if value else None
        )

    athlete_consistency = None
    if consistency:
        ratios = consistency.recency.recent_to_baseline
        weekly = consistency.recency.weekly_volume
        athlete_consistency = AthleteConsistencyContext(
            active_week_ratio=consistency.active_week_ratio,
            activities_per_week=consistency.activities_per_week,
            longest_inactivity_gap_days=consistency.longest_inactivity_gap_days,
            days_since_last_activity=consistency.days_since_last_activity,
            recent_activities_per_week=weekly.activities_per_week,
            recent_moving_time_seconds_per_week=weekly.moving_time_seconds_per_week,
            recent_distance_meters_per_week=weekly.distance_meters_per_week,
            recent_to_baseline_activities_ratio=ratios.activities_per_week_ratio
            if ratios
            else None,
            recent_to_baseline_moving_time_ratio=ratios.moving_time_seconds_per_week_ratio
            if ratios
            else None,
            recent_to_baseline_distance_ratio=ratios.distance_meters_per_week_ratio
            if ratios
            else None,
        )

    def breakdown_key(item) -> tuple[float, float, str, str]:
        return (
            -(item.distance_meters or -1),
            -(item.proportion or -1),
            getattr(item, "characteristic", ""),
            item.value,
        )

    def breakdowns(values, maximum, technical=False):
        projected = []
        for item in bounded(sorted(values, key=breakdown_key), maximum):
            fields = dict(
                value=clip(item.value),
                distance_meters=item.distance_meters,
                proportion=item.proportion,
            )
            projected.append(
                TechnicalBreakdownContext(
                    characteristic=clip(item.characteristic), **fields
                )
                if technical
                else BreakdownContext(**fields)
            )
        return projected

    components: list[ScoreComponentContext] = []

    def add_components(prefix, values, athlete=False):
        for item in values:
            evidence = "; ".join(item.evidence) if athlete else item.evidence_summary
            components.append(
                ScoreComponentContext(
                    component=clip(f"{prefix}.{item.name}"),
                    score=item.score,
                    evidence_available=True if athlete else item.evidence_available,
                    evidence_summary=clip(evidence),
                )
            )

    add_components("difficulty", scorecard.difficulty.components)
    add_components("athlete_fit", scorecard.athlete_fit.components, athlete=True)
    add_components("excitement", scorecard.excitement.components)
    add_components("preference_alignment", scorecard.preference_alignment.components)
    add_components("confidence", scorecard.confidence.components)
    components = bounded(components, MAX_SCORE_COMPONENTS)

    warnings = [
        *ranked_recommendation.warnings,
        *candidate.warnings,
        *scorecard.difficulty.warnings,
        *scorecard.athlete_fit.warnings,
        *scorecard.excitement.warnings,
        *scorecard.preference_alignment.warnings,
    ]
    warnings = bounded(sorted({clip(item) for item in warnings}), MAX_WARNINGS)

    context = RecommendationReasoningContext(
        recommendation=RankedRecommendationContext(
            rank=ranked_recommendation.rank,
            final_score=ranked_recommendation.final_score,
            ranking_version=clip(scorecard.ranking_version),
        ),
        planning_preferences=PlanningPreferencesContext(
            activity_kind=planning_request.activity_kind,
            target_distance_meters=planning_request.target_distance_meters,
            target_duration_seconds=planning_request.target_duration_seconds,
            desired_challenge=planning_request.desired_challenge,
            route_shape=planning_request.route_shape,
            novelty_preference=planning_request.novelty_preference,
            planning_area_display_name=clip(
                planning_request.planning_area.display_name
            ),
        ),
        athlete=AthleteContext(
            activity_kind=planning_request.activity_kind,
            matching_activity_sample_count=summary.activity_count if summary else 0,
            distance_meters=percentile(summary.capability_ranges.distance_meters)
            if summary
            else None,
            moving_time_seconds=percentile(
                summary.capability_ranges.moving_time_seconds
            )
            if summary
            else None,
            elevation_gain_meters=percentile(
                summary.capability_ranges.elevation_gain_meters
            )
            if summary
            else None,
            elevation_gain_meters_per_km=percentile(
                summary.capability_ranges.elevation_gain_meters_per_km
            )
            if summary
            else None,
            consistency=athlete_consistency,
        ),
        route_facts=RouteFactsContext(
            name=clip(candidate.name),
            activity_kind=candidate.activity_kind,
            distance_meters=candidate.distance_meters,
            estimated_duration_seconds=candidate.estimated_duration_seconds,
            elevation_gain_meters=candidate.elevation_gain_meters,
            elevation_loss_meters=candidate.elevation_loss_meters,
            route_shape=candidate.route_shape,
            data_confidence=candidate.data_confidence,
            surfaces=breakdowns(candidate.surface_breakdown, MAX_BREAKDOWN_ENTRIES),
            way_types=breakdowns(candidate.way_type_breakdown, MAX_BREAKDOWN_ENTRIES),
            technical_characteristics=breakdowns(
                candidate.technical_breakdown, MAX_TECHNICAL_ENTRIES, True
            ),
            provenance=bounded(
                [
                    ProvenanceContext(
                        provider=clip(p.provider),
                        attribution=clip(p.attribution),
                        provider_profile=clip(p.provider_profile)
                        if p.provider_profile
                        else None,
                    )
                    for p in sorted(
                        candidate.provenance,
                        key=lambda p: (
                            p.provider,
                            p.attribution,
                            p.provider_profile or "",
                        ),
                    )
                ],
                MAX_BREAKDOWN_ENTRIES,
            ),
        ),
        scorecard=ScorecardContext(
            difficulty=scorecard.difficulty.score,
            athlete_fit=scorecard.athlete_fit.score,
            athlete_fit_status=scorecard.athlete_fit.status,
            novelty=NoveltyContext(
                status=scorecard.novelty.status,
                score=scorecard.novelty.novelty_score,
                confidence=scorecard.novelty.confidence,
                geometry_coverage_ratio=scorecard.novelty.geometry_coverage_ratio,
            ),
            excitement=scorecard.excitement.score,
            preference_alignment=scorecard.preference_alignment.score,
            confidence=scorecard.confidence.score,
            final_score=scorecard.final_score,
            components=components,
        ),
        evidence_limitations=EvidenceLimitationsContext(
            warnings=warnings,
            strings_truncated=clipped,
            collections_truncated=collections_truncated,
        ),
    )
    if len(context.model_dump_json()) > MAX_REASONING_CONTEXT_CHARACTERS:
        raise ReasoningContextConstructionError(
            "reasoning context exceeds the v1 character limit"
        )
    return context
