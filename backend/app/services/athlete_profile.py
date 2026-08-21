from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from math import floor, fsum
from zoneinfo import ZoneInfo

from app.domain.activities import ActivityKind
from app.domain.athlete_profile import (
    ActivityAnalysisRecord,
    ActivityCapabilityRanges,
    ActivityKindSummary,
    ActivityVolume,
    AthleteProfile,
    ConsistencySignals,
    DominantActivityResult,
    HistoricalBaselineSignals,
    RecencySignals,
    RecentToBaselineRatios,
    RepresentativeRange,
    WeeklyActivityVolume,
)
from app.domain.calendar import (
    calendar_period_bounds,
    calendar_week_bucket_count,
    monday_week_start,
)

RECENT_WINDOW_DAYS = 28
MIN_BASELINE_DAYS = 28

_PACE_ACTIVITY_KINDS = frozenset(
    {
        ActivityKind.WALKING,
        ActivityKind.RUNNING,
        ActivityKind.TRAIL_RUNNING,
        ActivityKind.HIKING,
    }
)
_SPEED_ACTIVITY_KINDS = frozenset(
    {
        ActivityKind.ROAD_CYCLING,
        ActivityKind.GRAVEL_CYCLING,
        ActivityKind.MOUNTAIN_BIKING,
        ActivityKind.ALPINE_SKIING,
        ActivityKind.BACKCOUNTRY_SKIING,
        ActivityKind.NORDIC_SKIING,
    }
)


def calculate_representative_range(
    values: Iterable[int | float],
) -> RepresentativeRange | None:
    """Build a range using linear interpolation over sorted observations.

    Percentile position is ``(sample_size - 1) * percentile``. A fractional
    position is interpolated between the adjacent observations. This explicit
    rule keeps results independent of third-party statistical defaults.
    """

    observations = sorted(float(value) for value in values)
    if not observations:
        return None

    def percentile(fraction: float) -> float:
        position = (len(observations) - 1) * fraction
        lower_index = floor(position)
        upper_index = min(lower_index + 1, len(observations) - 1)
        weight = position - lower_index
        return (
            observations[lower_index] * (1 - weight)
            + observations[upper_index] * weight
        )

    return RepresentativeRange(
        sample_size=len(observations),
        p25=percentile(0.25),
        median=percentile(0.5),
        p75=percentile(0.75),
        p90=percentile(0.9),
    )


def calculate_activity_summaries(
    activities: Iterable[ActivityAnalysisRecord],
    *,
    period_start: date,
    period_end: date,
    timezone: str,
) -> AthleteProfile:
    """Summarize canonical activity facts within an inclusive calendar period."""

    bounds = calendar_period_bounds(period_start, period_end, timezone)
    zone = ZoneInfo(timezone)
    grouped: dict[ActivityKind, list[ActivityAnalysisRecord]] = defaultdict(list)
    unsupported_count = 0

    for activity in activities:
        if not bounds.start_at <= activity.started_at < bounds.end_at_exclusive:
            continue
        if activity.activity_kind is None:
            unsupported_count += 1
            continue
        grouped[activity.activity_kind].append(activity)

    summaries = [
        _summarize_activity_kind(activity_kind, records, zone)
        for activity_kind, records in sorted(
            grouped.items(), key=lambda item: item[0].value
        )
    ]
    consistency_signals = [
        calculate_consistency_signals(
            activity_kind,
            records,
            period_start=period_start,
            period_end=period_end,
            timezone=timezone,
        )
        for activity_kind, records in sorted(
            grouped.items(), key=lambda item: item[0].value
        )
    ]
    return AthleteProfile(
        period_start=period_start,
        period_end=period_end,
        timezone=timezone,
        activities_analyzed=sum(summary.activity_count for summary in summaries),
        unsupported_activities_excluded=unsupported_count,
        activity_summaries=summaries,
        dominant_activity=calculate_dominant_activity(summaries),
        consistency_signals=consistency_signals,
    )


def calculate_consistency_signals(
    activity_kind: ActivityKind,
    activities: Iterable[ActivityAnalysisRecord],
    *,
    period_start: date,
    period_end: date,
    timezone: str,
) -> ConsistencySignals:
    """Calculate period-wide and recent signals for one represented kind."""

    bounds = calendar_period_bounds(period_start, period_end, timezone)
    zone = ZoneInfo(timezone)
    records_with_dates = sorted(
        (
            (activity, activity.started_at.astimezone(zone).date())
            for activity in activities
            if activity.activity_kind is activity_kind
            and bounds.start_at <= activity.started_at < bounds.end_at_exclusive
        ),
        key=lambda item: item[1],
    )
    if not records_with_dates:
        raise ValueError("activities must contain the requested activity kind")

    period_days = (period_end - period_start).days + 1
    calendar_weeks = calendar_week_bucket_count(period_start, period_end)
    local_dates = sorted({local_date for _, local_date in records_with_dates})
    active_weeks = len({monday_week_start(local_date) for local_date in local_dates})

    effective_recent_days = min(RECENT_WINDOW_DAYS, period_days)
    recent_start = period_end - timedelta(days=effective_recent_days - 1)
    recent_records = [
        activity
        for activity, local_date in records_with_dates
        if local_date >= recent_start
    ]
    recent_volume = _activity_volume(recent_records, zone)
    recent_weekly_volume = _weekly_activity_volume(
        recent_volume, effective_recent_days
    )

    baseline_days = period_days - effective_recent_days
    baseline: HistoricalBaselineSignals | None = None
    recent_to_baseline: RecentToBaselineRatios | None = None
    if baseline_days >= MIN_BASELINE_DAYS:
        baseline_end = recent_start - timedelta(days=1)
        baseline_records = [
            activity
            for activity, local_date in records_with_dates
            if local_date < recent_start
        ]
        baseline_volume = _activity_volume(baseline_records, zone)
        baseline_weekly_volume = _weekly_activity_volume(
            baseline_volume, baseline_days
        )
        baseline = HistoricalBaselineSignals(
            period_start=period_start,
            period_end=baseline_end,
            effective_days=baseline_days,
            volume=baseline_volume,
            weekly_volume=baseline_weekly_volume,
        )
        recent_to_baseline = RecentToBaselineRatios(
            activities_per_week_ratio=_safe_ratio(
                recent_weekly_volume.activities_per_week,
                baseline_weekly_volume.activities_per_week,
            ),
            moving_time_seconds_per_week_ratio=_safe_ratio(
                recent_weekly_volume.moving_time_seconds_per_week,
                baseline_weekly_volume.moving_time_seconds_per_week,
            ),
            distance_meters_per_week_ratio=_safe_ratio(
                recent_weekly_volume.distance_meters_per_week,
                baseline_weekly_volume.distance_meters_per_week,
            ),
        )

    between_activity_gaps = [
        (later - earlier).days - 1
        for earlier, later in zip(local_dates, local_dates[1:], strict=False)
    ]
    longest_inactivity_gap_days = max(
        (local_dates[0] - period_start).days,
        (period_end - local_dates[-1]).days,
        *between_activity_gaps,
    )

    return ConsistencySignals(
        activity_kind=activity_kind,
        calendar_weeks=calendar_weeks,
        active_week_ratio=active_weeks / calendar_weeks,
        activities_per_week=len(records_with_dates) * 7 / period_days,
        longest_inactivity_gap_days=longest_inactivity_gap_days,
        days_since_last_activity=(period_end - local_dates[-1]).days,
        recency=RecencySignals(
            nominal_window_days=RECENT_WINDOW_DAYS,
            effective_window_days=effective_recent_days,
            window_start=recent_start,
            window_end=period_end,
            volume=recent_volume,
            weekly_volume=recent_weekly_volume,
            baseline=baseline,
            recent_to_baseline=recent_to_baseline,
        ),
    )


def calculate_dominant_activity(
    summaries: Iterable[ActivityKindSummary],
) -> DominantActivityResult | None:
    """Select the dominant kind from already-calculated supported summaries."""

    represented_summaries = list(summaries)
    if not represented_summaries:
        return None

    # Product ranking: moving time, then count, then distance, all descending.
    # ActivityKind.value ascending is only a stable technical fallback when every
    # product metric ties; it is not an additional product signal.
    dominant = min(
        represented_summaries,
        key=lambda summary: (
            -summary.total_moving_time_seconds,
            -summary.activity_count,
            -summary.total_distance_meters,
            summary.activity_kind.value,
        ),
    )
    total_moving_time_seconds = sum(
        summary.total_moving_time_seconds for summary in represented_summaries
    )
    moving_time_share = (
        dominant.total_moving_time_seconds / total_moving_time_seconds
        if total_moving_time_seconds
        else 0.0
    )

    return DominantActivityResult(
        activity_kind=dominant.activity_kind,
        total_moving_time_seconds=dominant.total_moving_time_seconds,
        activity_count=dominant.activity_count,
        total_distance_meters=dominant.total_distance_meters,
        moving_time_share=moving_time_share,
    )


def _summarize_activity_kind(
    activity_kind: ActivityKind,
    activities: list[ActivityAnalysisRecord],
    zone: ZoneInfo,
) -> ActivityKindSummary:
    distances = [activity.distance_meters for activity in activities]
    moving_times = [activity.moving_time_seconds for activity in activities]
    elevations = [
        activity.elevation_gain_meters
        for activity in activities
        if activity.elevation_gain_meters is not None
    ]
    climbing_densities = [
        activity.elevation_gain_meters / (activity.distance_meters / 1_000)
        for activity in activities
        if activity.distance_meters > 0
        and activity.elevation_gain_meters is not None
    ]
    pace_seconds_per_km = [
        activity.moving_time_seconds / (activity.distance_meters / 1_000)
        for activity in activities
        if activity_kind in _PACE_ACTIVITY_KINDS
        and activity.distance_meters > 0
        and activity.moving_time_seconds > 0
    ]
    moving_speeds = [
        activity.distance_meters / activity.moving_time_seconds
        for activity in activities
        if activity_kind in _SPEED_ACTIVITY_KINDS
        and activity.distance_meters > 0
        and activity.moving_time_seconds > 0
    ]
    distance_range = calculate_representative_range(distances)
    moving_time_range = calculate_representative_range(moving_times)
    elevation_range = calculate_representative_range(elevations)
    assert distance_range is not None
    assert moving_time_range is not None
    active_week_starts: set[date] = set()
    for activity in activities:
        local_date = activity.started_at.astimezone(zone).date()
        active_week_starts.add(monday_week_start(local_date))

    return ActivityKindSummary(
        activity_kind=activity_kind,
        activity_count=len(activities),
        total_distance_meters=fsum(distances),
        total_moving_time_seconds=sum(moving_times),
        total_elevation_gain_meters=fsum(elevations) if elevations else None,
        elevation_sample_count=len(elevations),
        active_weeks=len(active_week_starts),
        median_distance_meters=distance_range.median,
        median_moving_time_seconds=moving_time_range.median,
        median_elevation_gain_meters=(
            elevation_range.median if elevation_range else None
        ),
        capability_ranges=ActivityCapabilityRanges(
            distance_meters=distance_range,
            moving_time_seconds=moving_time_range,
            elevation_gain_meters=elevation_range,
            elevation_gain_meters_per_km=calculate_representative_range(
                climbing_densities
            ),
            pace_seconds_per_km=calculate_representative_range(
                pace_seconds_per_km
            ),
            average_moving_speed_meters_per_second=calculate_representative_range(
                moving_speeds
            ),
        ),
    )


def _activity_volume(
    activities: Iterable[ActivityAnalysisRecord], zone: ZoneInfo
) -> ActivityVolume:
    records = list(activities)
    return ActivityVolume(
        activity_count=len(records),
        moving_time_seconds=sum(activity.moving_time_seconds for activity in records),
        distance_meters=fsum(activity.distance_meters for activity in records),
        active_weeks=len(
            {
                monday_week_start(activity.started_at.astimezone(zone).date())
                for activity in records
            }
        ),
    )


def _weekly_activity_volume(
    volume: ActivityVolume, effective_days: int
) -> WeeklyActivityVolume:
    weeklyization_factor = 7 / effective_days
    return WeeklyActivityVolume(
        activities_per_week=volume.activity_count * weeklyization_factor,
        moving_time_seconds_per_week=(
            volume.moving_time_seconds * weeklyization_factor
        ),
        distance_meters_per_week=volume.distance_meters * weeklyization_factor,
    )


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator > 0 else None
