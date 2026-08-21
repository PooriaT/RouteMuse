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


class ActivityVolume(BaseModel):
    """Transparent activity totals for a bounded calendar window."""

    activity_count: int = Field(ge=0)
    moving_time_seconds: int = Field(ge=0)
    distance_meters: float = Field(ge=0)
    active_weeks: int = Field(ge=0)


class WeeklyActivityVolume(BaseModel):
    """Activity volume normalized to seven days of available history."""

    activities_per_week: float = Field(ge=0)
    moving_time_seconds_per_week: float = Field(ge=0)
    distance_meters_per_week: float = Field(ge=0)


class HistoricalBaselineSignals(BaseModel):
    """Pre-recent-window volume and its weeklyized representation."""

    period_start: date
    period_end: date
    effective_days: int = Field(ge=1)
    volume: ActivityVolume
    weekly_volume: WeeklyActivityVolume


class RecentToBaselineRatios(BaseModel):
    """Dimensionless recent weekly volume divided by baseline weekly volume."""

    activities_per_week_ratio: float | None = Field(default=None, ge=0)
    moving_time_seconds_per_week_ratio: float | None = Field(default=None, ge=0)
    distance_meters_per_week_ratio: float | None = Field(default=None, ge=0)


class RecencySignals(BaseModel):
    """Recent volume, comparable baseline, and transparent volume ratios."""

    nominal_window_days: int = Field(ge=1)
    effective_window_days: int = Field(ge=1)
    window_start: date
    window_end: date
    volume: ActivityVolume
    weekly_volume: WeeklyActivityVolume
    baseline: HistoricalBaselineSignals | None = None
    recent_to_baseline: RecentToBaselineRatios | None = None


class ConsistencySignals(BaseModel):
    """Explainable period-wide consistency and recency for one activity kind."""

    activity_kind: ActivityKind
    calendar_weeks: int = Field(ge=1)
    active_week_ratio: float = Field(ge=0, le=1)
    activities_per_week: float = Field(ge=0)
    longest_inactivity_gap_days: int = Field(ge=0)
    days_since_last_activity: int = Field(ge=0)
    recency: RecencySignals


class AthleteProfile(BaseModel):
    period_start: date
    period_end: date
    timezone: str
    activities_analyzed: int = Field(default=0, ge=0)
    unsupported_activities_excluded: int = Field(default=0, ge=0)
    activity_summaries: list[ActivityKindSummary] = Field(default_factory=list)
    dominant_activity: DominantActivityResult | None = None
    consistency_signals: list[ConsistencySignals] = Field(default_factory=list)
