from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from math import fsum
from statistics import median
from zoneinfo import ZoneInfo

from app.domain.activities import ActivityKind
from app.domain.athlete_profile import (
    ActivityAnalysisRecord,
    ActivityKindSummary,
    AthleteProfile,
    DominantActivityResult,
)
from app.domain.calendar import calendar_period_bounds


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
    return AthleteProfile(
        period_start=period_start,
        period_end=period_end,
        timezone=timezone,
        activities_analyzed=sum(summary.activity_count for summary in summaries),
        unsupported_activities_excluded=unsupported_count,
        activity_summaries=summaries,
        dominant_activity=calculate_dominant_activity(summaries),
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
    active_week_starts: set[date] = set()
    for activity in activities:
        local_date = activity.started_at.astimezone(zone).date()
        active_week_starts.add(local_date - timedelta(days=local_date.weekday()))

    return ActivityKindSummary(
        activity_kind=activity_kind,
        activity_count=len(activities),
        total_distance_meters=fsum(distances),
        total_moving_time_seconds=sum(moving_times),
        total_elevation_gain_meters=fsum(elevations) if elevations else None,
        elevation_sample_count=len(elevations),
        active_weeks=len(active_week_starts),
        median_distance_meters=median(distances),
        median_moving_time_seconds=median(moving_times),
        median_elevation_gain_meters=median(elevations) if elevations else None,
    )
