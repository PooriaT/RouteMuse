from datetime import date

from pydantic import AwareDatetime, BaseModel, Field

from app.domain.activities import ActivityKind


class ActivityAnalysisRecord(BaseModel):
    """Provider-neutral historical activity facts used by athlete analysis."""

    activity_kind: ActivityKind | None
    started_at: AwareDatetime
    distance_meters: float = Field(ge=0)
    moving_time_seconds: int = Field(ge=0)
    elevation_gain_meters: float | None = Field(default=None, ge=0)


class ActivityKindSummary(BaseModel):
    """Deterministic aggregates for one represented RouteMuse activity kind."""

    activity_kind: ActivityKind
    activity_count: int = Field(ge=1)
    total_distance_meters: float = Field(ge=0)
    total_moving_time_seconds: int = Field(ge=0)
    total_elevation_gain_meters: float | None = Field(default=None, ge=0)
    elevation_sample_count: int = Field(ge=0)
    active_weeks: int = Field(ge=1)
    median_distance_meters: float = Field(ge=0)
    median_moving_time_seconds: float = Field(ge=0)
    median_elevation_gain_meters: float | None = Field(default=None, ge=0)


class AthleteProfile(BaseModel):
    period_start: date
    period_end: date
    timezone: str
    activities_analyzed: int = Field(default=0, ge=0)
    unsupported_activities_excluded: int = Field(default=0, ge=0)
    activity_summaries: list[ActivityKindSummary] = Field(default_factory=list)
