from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.calendar import resolve_iana_timezone
from app.domain.planning import RoutePlanningRequest
from app.domain.routes import RouteCandidate

BoundedScore = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class ScoreComponent(BaseModel):
    """One independently explainable factual contribution to a route score."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    score: BoundedScore | None
    weight: BoundedScore
    evidence_available: bool
    evidence_summary: str


class RouteDifficultyAssessment(BaseModel):
    """Versioned intrinsic difficulty plus an explicit evidence audit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    score: BoundedScore
    components: list[ScoreComponent]
    evidence_coverage: BoundedScore
    scoring_version: str
    warnings: list[str] = Field(default_factory=list)


class ExcitementComponent(BaseModel):
    """One reviewable heuristic contribution backed by candidate facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    score: BoundedScore | None
    base_weight: BoundedScore
    evidence_available: bool
    evidence_summary: str


class ExcitementAssessment(BaseModel):
    """Versioned excitement heuristic with an explicit evidence audit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    score: BoundedScore | None
    components: list[ExcitementComponent]
    evidence_coverage: BoundedScore
    scoring_version: str
    warnings: list[str] = Field(default_factory=list)


class AthleteFitStatus(StrEnum):
    """Whether athlete-fit evidence permits a numeric assessment."""

    SCORED = "scored"
    INSUFFICIENT_HISTORY = "insufficient_history"
    UNSUPPORTED_ACTIVITY = "unsupported_activity"


class AthleteFitComponent(BaseModel):
    """One transparent athlete capability or consistency fit signal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    score: BoundedScore
    evidence: list[str] = Field(min_length=1)


class AthleteFitAssessment(BaseModel):
    """Versioned athlete-specific fit, distinct from intrinsic difficulty."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    score: BoundedScore | None
    confidence: BoundedScore
    components: list[AthleteFitComponent]
    status: AthleteFitStatus
    scoring_version: str
    warnings: list[str] = Field(default_factory=list)


class NoveltyStatus(StrEnum):
    AVAILABLE = "available"
    INSUFFICIENT_HISTORY = "insufficient_history"


class NoveltyAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: NoveltyStatus
    novelty_score: BoundedScore | None = None
    confidence: BoundedScore
    eligible_activity_count: int = Field(ge=0)
    geometry_activity_count: int = Field(ge=0)
    missing_geometry_activity_count: int = Field(ge=0)
    geometry_coverage_ratio: BoundedScore


class RecommendationExplanation(BaseModel):
    summary: str
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RecommendationRequest(BaseModel):
    """Planning inputs plus the inclusive persisted-history calendar period."""

    model_config = ConfigDict(extra="forbid")

    planning_request: RoutePlanningRequest
    start_date: date
    end_date: date
    timezone: str

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        resolve_iana_timezone(value)
        return value

    @model_validator(mode="after")
    def validate_period(self) -> "RecommendationRequest":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        if self.end_date == date.max:
            raise ValueError("end_date is outside the supported range")
        return self


class PreferenceAlignmentAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    score: BoundedScore | None
    components: list[ScoreComponent]
    evidence_coverage: BoundedScore
    scoring_version: str
    warnings: list[str] = Field(default_factory=list)


class RecommendationConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    score: BoundedScore
    components: list[ScoreComponent]
    scoring_version: str


class RecommendationScorecard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    final_score: BoundedScore
    ranking_version: str
    difficulty: RouteDifficultyAssessment
    athlete_fit: AthleteFitAssessment
    novelty: NoveltyAssessment
    excitement: ExcitementAssessment
    preference_alignment: PreferenceAlignmentAssessment
    confidence: RecommendationConfidence


class RankedRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rank: int = Field(gt=0)
    candidate: RouteCandidate
    final_score: BoundedScore
    difficulty: RouteDifficultyAssessment
    athlete_fit: AthleteFitAssessment
    novelty: NoveltyAssessment
    excitement: ExcitementAssessment
    preference_alignment: PreferenceAlignmentAssessment
    confidence: RecommendationConfidence
    scorecard: RecommendationScorecard
    warnings: list[str] = Field(default_factory=list)


class RecommendationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recommendations: list[RankedRecommendation]
    requested_recommendations: int = Field(gt=0)
    generated_candidates: int = Field(ge=0)
    ranking_version: str
    warnings: list[str] = Field(default_factory=list)
