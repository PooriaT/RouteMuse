from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

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


class RecommendationExplanation(BaseModel):
    summary: str
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
