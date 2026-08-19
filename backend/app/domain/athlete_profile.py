from datetime import date

from pydantic import BaseModel, Field

from app.domain.activities import ActivityKind


class EffortStatistics(BaseModel):
    typical_distance_meters: float | None = None
    strong_distance_meters: float | None = None
    typical_duration_seconds: int | None = None


class AthleteProfile(BaseModel):
    period_start: date
    period_end: date
    dominant_activity: ActivityKind | None = None
    activities_analyzed: int = Field(default=0, ge=0)
    activity_counts: dict[ActivityKind, int] = Field(default_factory=dict)
    moving_time_seconds: dict[ActivityKind, int] = Field(default_factory=dict)
    distance_meters: dict[ActivityKind, float] = Field(default_factory=dict)
    elevation_gain_meters: dict[ActivityKind, float] = Field(default_factory=dict)
    activities_per_week: float | None = None
    consistency_indicators: dict[str, float] = Field(default_factory=dict)
    representative_efforts: dict[ActivityKind, EffortStatistics] = Field(
        default_factory=dict
    )
    recent_activity_indicators: dict[str, float] = Field(default_factory=dict)
