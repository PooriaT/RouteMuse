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


class RepresentativeRange(BaseModel):
    """Percentile distribution for one metric with its valid sample count."""

    sample_size: int = Field(ge=1)
    p25: float
    median: float
    p75: float
    p90: float


class ActivityCapabilityRanges(BaseModel):
    """Typed representative per-activity ranges for one activity kind."""

    distance_meters: RepresentativeRange
    moving_time_seconds: RepresentativeRange
    elevation_gain_meters: RepresentativeRange | None = None
    elevation_gain_meters_per_km: RepresentativeRange | None = None
    pace_seconds_per_km: RepresentativeRange | None = None
    average_moving_speed_meters_per_second: RepresentativeRange | None = None


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
    capability_ranges: ActivityCapabilityRanges


class DominantActivityResult(BaseModel):
    """The selected activity kind and the facts supporting that selection."""

    activity_kind: ActivityKind
    total_moving_time_seconds: int = Field(ge=0)
    activity_count: int = Field(ge=1)
    total_distance_meters: float = Field(ge=0)
    moving_time_share: float = Field(ge=0, le=1)


class AthleteProfile(BaseModel):
    period_start: date
    period_end: date
    timezone: str
    activities_analyzed: int = Field(default=0, ge=0)
    unsupported_activities_excluded: int = Field(default=0, ge=0)
    activity_summaries: list[ActivityKindSummary] = Field(default_factory=list)
    dominant_activity: DominantActivityResult | None = None
