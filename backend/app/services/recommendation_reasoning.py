"""Post-ranking reasoning enrichment with a deterministic supported fallback."""

from pydantic import ValidationError

from app.domain.reasoning_context import (
    REASONING_CONTEXT_VERSION,
    RecommendationReasoningContext,
)
from app.domain.recommendations import (
    RankedRecommendation,
    ReasoningSource,
    RecommendationQualitativeTag,
    RecommendationReasoning,
    RecommendationReasoningEnvelope,
)
from app.integrations.contracts import LlmProvider
from app.integrations.llm.errors import (
    LlmConfigurationError,
    LlmMalformedResponseError,
    LlmModelUnavailableError,
    LlmProviderError,
    LlmTimeoutError,
)
from app.services.reasoning_context import build_reasoning_context

STRONG_ATHLETE_FIT_THRESHOLD = 0.75
CLOSE_TO_TARGET_THRESHOLD = 0.80
HIGH_CLIMBING_THRESHOLD = 0.65
NOVEL_THRESHOLD = 0.70
FAMILIAR_THRESHOLD = 0.30
LIMITED_EVIDENCE_THRESHOLD = 0.50
MAX_FALLBACK_REASONS = 4
MAX_FALLBACK_HIGHLIGHTS = 5


def grounded_qualitative_tags(
    context: RecommendationReasoningContext,
) -> list[RecommendationQualitativeTag]:
    """Derive schema tags in a fixed order from centralized explicit thresholds."""
    components = {item.component: item for item in context.scorecard.components}
    tags: list[RecommendationQualitativeTag] = []
    distance = components.get("preference_alignment.target_distance")
    if (
        distance
        and distance.score is not None
        and distance.score >= CLOSE_TO_TARGET_THRESHOLD
    ):
        tags.append(RecommendationQualitativeTag.CLOSE_TO_TARGET)
    if (
        context.scorecard.athlete_fit is not None
        and context.scorecard.athlete_fit >= STRONG_ATHLETE_FIT_THRESHOLD
    ):
        tags.append(RecommendationQualitativeTag.STRONG_ATHLETE_FIT)
    climbing = components.get("difficulty.climbing")
    if (
        context.route_facts.elevation_gain_meters is not None
        and climbing
        and climbing.score is not None
        and climbing.score >= HIGH_CLIMBING_THRESHOLD
    ):
        tags.append(RecommendationQualitativeTag.HIGH_CLIMBING)
    known_surfaces = [
        item.value
        for item in context.route_facts.surfaces
        if (item.proportion or 0) > 0 or (item.distance_meters or 0) > 0
    ]
    if len(set(known_surfaces)) >= 2:
        tags.append(RecommendationQualitativeTag.MIXED_SURFACE)
    if context.route_facts.technical_characteristics:
        tags.append(RecommendationQualitativeTag.TECHNICAL_TERRAIN)
    novelty = context.scorecard.novelty.score
    if novelty is not None and novelty >= NOVEL_THRESHOLD:
        tags.append(RecommendationQualitativeTag.NOVEL)
    elif novelty is not None and novelty <= FAMILIAR_THRESHOLD:
        tags.append(RecommendationQualitativeTag.FAMILIAR)
    confidence = getattr(context.scorecard, "confidence", 1.0)
    novelty_confidence = getattr(context.scorecard.novelty, "confidence", 1.0)
    limitations = context.evidence_limitations
    if (
        confidence < LIMITED_EVIDENCE_THRESHOLD
        or novelty_confidence < LIMITED_EVIDENCE_THRESHOLD
        or limitations.warnings
        or limitations.collections_truncated
        or limitations.strings_truncated
        or any(not item.evidence_available for item in context.scorecard.components)
    ):
        tags.append(RecommendationQualitativeTag.LIMITED_EVIDENCE)
    return tags


def build_deterministic_reasoning(
    context: RecommendationReasoningContext,
) -> RecommendationReasoning:
    """Build stable, factual reasoning without I/O, time, randomness, or inference."""
    facts = context.route_facts
    scores = context.scorecard
    preferences = context.planning_preferences
    elevation = (
        f" and {facts.elevation_gain_meters:.0f} m elevation gain"
        if facts.elevation_gain_meters is not None
        else ""
    )
    summary = (
        f"Rank {context.recommendation.rank} {facts.activity_kind.value} route: "
        f"{facts.distance_meters / 1000:.1f} km{elevation}; athlete-fit "
        f"{scores.athlete_fit:.2f}."
        if scores.athlete_fit is not None
        else f"Rank {context.recommendation.rank} {facts.activity_kind.value} route: "
        f"{facts.distance_meters / 1000:.1f} km{elevation}."
    )

    reasons: list[str] = []
    if scores.athlete_fit is not None:
        reasons.append(f"Athlete-fit score is {scores.athlete_fit:.2f}.")
    if scores.preference_alignment is not None:
        reasons.append(
            "Requested-preference alignment score is "
            f"{scores.preference_alignment:.2f}."
        )
    challenge = next(
        (
            c
            for c in scores.components
            if c.component == "preference_alignment.desired_challenge"
        ),
        None,
    )
    if (
        preferences.desired_challenge is not None
        and challenge
        and challenge.score is not None
    ):
        reasons.append(
            f"{preferences.desired_challenge.value} challenge alignment score is "
            f"{challenge.score:.2f}."
        )
    if preferences.novelty_preference is not None and scores.novelty.score is not None:
        reasons.append(
            f"Novelty score is {scores.novelty.score:.2f} for the requested "
            f"{preferences.novelty_preference.value} preference."
        )
    if scores.excitement is not None:
        reasons.append(f"Excitement evidence score is {scores.excitement:.2f}.")
    reasons.append(f"Recommendation confidence is {scores.confidence:.2f}.")

    cautions = list(context.evidence_limitations.warnings)
    if (
        scores.novelty.score is None
        and "Novelty is unavailable from the supplied history." not in cautions
    ):
        cautions.append("Novelty is unavailable from the supplied history.")
    if scores.confidence < LIMITED_EVIDENCE_THRESHOLD:
        cautions.append(
            f"Recommendation confidence is limited at {scores.confidence:.2f}."
        )

    highlights = [f"Route distance: {facts.distance_meters / 1000:.1f} km."]
    if facts.elevation_gain_meters is not None:
        highlights.append(f"Elevation gain: {facts.elevation_gain_meters:.0f} m.")
    if facts.route_shape is not None:
        highlights.append(f"Route shape: {facts.route_shape.value}.")
    for surface in facts.surfaces[:2]:
        if (surface.proportion or 0) > 0 or (surface.distance_meters or 0) > 0:
            highlights.append(f"Known surface: {surface.value}.")
    if scores.novelty.score is not None:
        highlights.append(f"Known novelty score: {scores.novelty.score:.2f}.")

    return RecommendationReasoning(
        summary=summary,
        reasons=reasons[:MAX_FALLBACK_REASONS],
        cautions=cautions[:8],
        highlights=highlights[:MAX_FALLBACK_HIGHLIGHTS],
        qualitative_tags=grounded_qualitative_tags(context),
    )


def _warning_for(exc: LlmProviderError) -> str:
    if isinstance(exc, LlmConfigurationError):
        return "ollama_unconfigured_using_fallback"
    if isinstance(exc, LlmTimeoutError):
        return "ollama_timeout_using_fallback"
    if isinstance(exc, LlmMalformedResponseError):
        return "ollama_invalid_output_using_fallback"
    if isinstance(exc, LlmModelUnavailableError):
        return "ollama_model_unavailable_using_fallback"
    return "ollama_unavailable_using_fallback"


async def enrich_recommendations(
    recommendations: list[RankedRecommendation],
    planning_request,
    athlete_profile,
    llm_provider: LlmProvider | None,
    *,
    model: str | None = None,
) -> tuple[list[RankedRecommendation], list[str]]:
    """Sequentially enrich selected routes; one LLM failure disables later calls."""
    enabled = llm_provider is not None
    result: list[RankedRecommendation] = []
    warnings: list[str] = []
    if not enabled:
        warnings.append("ollama_unconfigured_using_fallback")
    for recommendation in recommendations:
        context = build_reasoning_context(
            recommendation, planning_request, athlete_profile
        )
        reasoning = None
        source = ReasoningSource.DETERMINISTIC_FALLBACK
        if enabled:
            try:
                reasoning = RecommendationReasoning.model_validate(
                    await llm_provider.explain(context)
                )
                source = ReasoningSource.OLLAMA
            except (LlmProviderError, ValidationError) as exc:
                warning = (
                    _warning_for(exc)
                    if isinstance(exc, LlmProviderError)
                    else "ollama_invalid_output_using_fallback"
                )
                if warning not in warnings:
                    warnings.append(warning)
                enabled = False
        if reasoning is None:
            reasoning = build_deterministic_reasoning(context)
        envelope = RecommendationReasoningEnvelope(
            source=source,
            reasoning=reasoning,
            context_version=REASONING_CONTEXT_VERSION,
            model=model if source is ReasoningSource.OLLAMA else None,
        )
        result.append(recommendation.model_copy(update={"reasoning": envelope}))
    return result, warnings
