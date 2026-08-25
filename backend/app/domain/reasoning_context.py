"""Bounded, provider-neutral facts supplied to recommendation explainers."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domain.activities import ActivityKind
from app.domain.planning import DesiredChallenge, NoveltyPreference
from app.domain.recommendations import AthleteFitStatus, BoundedScore, NoveltyStatus
from app.domain.routes import RouteShape

REASONING_CONTEXT_VERSION = "reasoning-context-v1"
MAX_REASONING_CONTEXT_CHARACTERS = 32_000
MAX_BREAKDOWN_ENTRIES = 8
MAX_TECHNICAL_ENTRIES = 12
MAX_SCORE_COMPONENTS = 24
MAX_WARNINGS = 16
MAX_CONTEXT_STRING_LENGTH = 300

ContextString = Annotated[str, StringConstraints(min_length=1, max_length=300)]


class _ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RankedRecommendationContext(_ContextModel):
    rank: int = Field(gt=0)
    final_score: BoundedScore
    ranking_version: ContextString


class PlanningPreferencesContext(_ContextModel):
    activity_kind: ActivityKind
    target_distance_meters: float | None
    target_duration_seconds: int | None
    desired_challenge: DesiredChallenge | None
    route_shape: RouteShape | None
    novelty_preference: NoveltyPreference | None
    planning_area_display_name: ContextString


class PercentileRangeContext(_ContextModel):
    sample_size: int = Field(ge=1)
    p25: float
    median: float
    p75: float
    p90: float


class AthleteConsistencyContext(_ContextModel):
    active_week_ratio: float = Field(ge=0, le=1)
    activities_per_week: float = Field(ge=0)
    longest_inactivity_gap_days: int = Field(ge=0)
    days_since_last_activity: int = Field(ge=0)
    recent_activities_per_week: float = Field(ge=0)
    recent_moving_time_seconds_per_week: float = Field(ge=0)
    recent_distance_meters_per_week: float = Field(ge=0)
    recent_to_baseline_activities_ratio: float | None
    recent_to_baseline_moving_time_ratio: float | None
    recent_to_baseline_distance_ratio: float | None


class AthleteContext(_ContextModel):
    activity_kind: ActivityKind
    matching_activity_sample_count: int = Field(ge=0)
    distance_meters: PercentileRangeContext | None
    moving_time_seconds: PercentileRangeContext | None
    elevation_gain_meters: PercentileRangeContext | None
    elevation_gain_meters_per_km: PercentileRangeContext | None
    consistency: AthleteConsistencyContext | None


class BreakdownContext(_ContextModel):
    value: ContextString
    distance_meters: float | None
    proportion: float | None


class TechnicalBreakdownContext(BreakdownContext):
    characteristic: ContextString


class ProvenanceContext(_ContextModel):
    provider: ContextString
    attribution: ContextString
    provider_profile: ContextString | None


class RouteFactsContext(_ContextModel):
    name: ContextString
    activity_kind: ActivityKind
    distance_meters: float
    estimated_duration_seconds: int | None
    elevation_gain_meters: float | None
    elevation_loss_meters: float | None
    route_shape: RouteShape | None
    data_confidence: BoundedScore | None
    surfaces: list[BreakdownContext] = Field(max_length=MAX_BREAKDOWN_ENTRIES)
    way_types: list[BreakdownContext] = Field(max_length=MAX_BREAKDOWN_ENTRIES)
    technical_characteristics: list[TechnicalBreakdownContext] = Field(
        max_length=MAX_TECHNICAL_ENTRIES
    )
    provenance: list[ProvenanceContext] = Field(max_length=MAX_BREAKDOWN_ENTRIES)


class ScoreComponentContext(_ContextModel):
    component: ContextString
    score: BoundedScore | None
    evidence_available: bool
    evidence_summary: ContextString


class NoveltyContext(_ContextModel):
    status: NoveltyStatus
    score: BoundedScore | None
    confidence: BoundedScore
    geometry_coverage_ratio: BoundedScore


class ScorecardContext(_ContextModel):
    difficulty: BoundedScore
    athlete_fit: BoundedScore | None
    athlete_fit_status: AthleteFitStatus
    novelty: NoveltyContext
    excitement: BoundedScore | None
    preference_alignment: BoundedScore | None
    confidence: BoundedScore
    final_score: BoundedScore
    components: list[ScoreComponentContext] = Field(max_length=MAX_SCORE_COMPONENTS)


class EvidenceLimitationsContext(_ContextModel):
    warnings: list[ContextString] = Field(max_length=MAX_WARNINGS)
    strings_truncated: bool
    collections_truncated: bool


class RecommendationReasoningContext(_ContextModel):
    """The complete and only application-data boundary visible to an LLM."""

    context_version: Literal["reasoning-context-v1"] = REASONING_CONTEXT_VERSION
    recommendation: RankedRecommendationContext
    planning_preferences: PlanningPreferencesContext
    athlete: AthleteContext
    route_facts: RouteFactsContext
    scorecard: ScorecardContext
    evidence_limitations: EvidenceLimitationsContext


class ReasoningContextConstructionError(ValueError):
    """A projected context could not satisfy the defensive serialized-size bound."""
