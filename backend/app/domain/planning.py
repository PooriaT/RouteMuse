from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.activities import ActivityKind
from app.domain.planning_areas import PlanningArea
from app.domain.routes import RouteShape


class DesiredChallenge(StrEnum):
    """The athlete's preferred challenge level, not measured route difficulty."""

    EASY = "easy"
    MODERATE = "moderate"
    HARD = "hard"


class NoveltyPreference(StrEnum):
    """The athlete's preference for familiar or novel routes."""

    FAMILIAR = "familiar"
    BALANCED = "balanced"
    NOVEL = "novel"


class RoutePlanningRequest(BaseModel):
    """Provider-independent inputs for future route planning."""

    model_config = ConfigDict(extra="forbid")

    planning_area: PlanningArea
    activity_kind: ActivityKind
    target_distance_meters: float | None = Field(
        default=None, gt=0, allow_inf_nan=False, strict=True
    )
    target_duration_seconds: int | None = Field(default=None, gt=0, strict=True)
    desired_challenge: DesiredChallenge | None = None
    route_shape: RouteShape | None = None
    novelty_preference: NoveltyPreference | None = None
