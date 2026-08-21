from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.domain.activities import ActivityKind
from app.domain.athlete_profile import ActivityAnalysisRecord, ConsistencySignals
from app.services.athlete_profile import (
    MIN_BASELINE_DAYS,
    RECENT_WINDOW_DAYS,
    calculate_activity_summaries,
)

PERIOD_START = date(2026, 1, 5)
PERIOD_END = date(2026, 3, 29)


def _activity(
    activity_kind: ActivityKind | None,
    local_date: date,
    *,
    count: int = 1,
    moving_time: int = 600,
    distance: float = 5_000.0,
) -> list[ActivityAnalysisRecord]:
    return [
        ActivityAnalysisRecord(
            activity_kind=activity_kind,
            started_at=datetime.combine(local_date, time(12), tzinfo=UTC)
            + timedelta(minutes=index),
            moving_time_seconds=moving_time,
            distance_meters=distance,
            elevation_gain_meters=50.0,
        )
        for index in range(count)
    ]


def _weekly_dates(start: date, weeks: int) -> list[date]:
    return [start + timedelta(weeks=index) for index in range(weeks)]


def _profile(
    activities: list[ActivityAnalysisRecord],
    *,
    period_start: date = PERIOD_START,
    period_end: date = PERIOD_END,
    timezone: str = "UTC",
):
    return calculate_activity_summaries(
        activities,
        period_start=period_start,
        period_end=period_end,
        timezone=timezone,
    )


def _signals(
    activities: list[ActivityAnalysisRecord],
    *,
    period_start: date = PERIOD_START,
    period_end: date = PERIOD_END,
    timezone: str = "UTC",
) -> ConsistencySignals:
    profile = _profile(
        activities,
        period_start=period_start,
        period_end=period_end,
        timezone=timezone,
    )
    assert len(profile.consistency_signals) == 1
    return profile.consistency_signals[0]


def test_consistent_weekly_pattern_has_full_ratio_and_short_gaps() -> None:
    activities = [
        activity
        for activity_date in _weekly_dates(PERIOD_START, 12)
        for activity in _activity(ActivityKind.RUNNING, activity_date)
    ]

    signals = _signals(activities)

    assert signals.calendar_weeks == 12
    assert signals.active_week_ratio == 1.0
    assert signals.activities_per_week == 1.0
    assert signals.longest_inactivity_gap_days == 6
    assert signals.days_since_last_activity == 6
    assert signals.recency.volume.activity_count == 4
    assert signals.recency.volume.active_weeks == 4


def test_partial_boundary_weeks_are_full_active_week_ratio_buckets() -> None:
    signals = _signals(
        [
            *_activity(ActivityKind.RUNNING, date(2026, 1, 2)),
            *_activity(ActivityKind.RUNNING, date(2026, 1, 8)),
        ],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 10),
    )

    assert signals.calendar_weeks == 2
    assert signals.active_week_ratio == 1.0
    assert signals.activities_per_week == pytest.approx(1.4)
    assert signals.recency.effective_window_days == 10


def test_historical_only_has_zero_recent_volume_and_baseline() -> None:
    activities = [
        activity
        for activity_date in _weekly_dates(PERIOD_START, 8)
        for activity in _activity(ActivityKind.ROAD_CYCLING, activity_date)
    ]

    signals = _signals(activities)
    baseline = signals.recency.baseline
    ratios = signals.recency.recent_to_baseline

    assert signals.recency.volume.activity_count == 0
    assert signals.recency.volume.moving_time_seconds == 0
    assert signals.recency.volume.distance_meters == 0.0
    assert baseline is not None
    assert baseline.effective_days == 56
    assert baseline.weekly_volume.activities_per_week == 1.0
    assert ratios is not None
    assert ratios.activities_per_week_ratio == 0.0
    assert ratios.moving_time_seconds_per_week_ratio == 0.0
    assert ratios.distance_meters_per_week_ratio == 0.0
    assert signals.days_since_last_activity == 34
    assert signals.longest_inactivity_gap_days == 34


@pytest.mark.parametrize(
    ("baseline_count", "recent_count", "expected_ratio"),
    [(1, 2, 2.0), (2, 1, 0.5)],
)
def test_recent_volume_is_compared_with_weekly_baseline(
    baseline_count: int, recent_count: int, expected_ratio: float
) -> None:
    activities = [
        activity
        for activity_date in _weekly_dates(PERIOD_START, 8)
        for activity in _activity(
            ActivityKind.RUNNING, activity_date, count=baseline_count
        )
    ]
    activities.extend(
        activity
        for activity_date in _weekly_dates(date(2026, 3, 2), 4)
        for activity in _activity(
            ActivityKind.RUNNING, activity_date, count=recent_count
        )
    )

    recency = _signals(activities).recency

    assert recency.weekly_volume.activities_per_week == recent_count
    assert recency.baseline is not None
    assert recency.baseline.weekly_volume.activities_per_week == baseline_count
    assert recency.recent_to_baseline is not None
    assert recency.recent_to_baseline.activities_per_week_ratio == expected_ratio
    assert (
        recency.recent_to_baseline.moving_time_seconds_per_week_ratio
        == expected_ratio
    )
    assert recency.recent_to_baseline.distance_meters_per_week_ratio == expected_ratio


def test_short_history_uses_effective_recent_window_without_baseline() -> None:
    period_start = date(2026, 3, 16)
    signals = _signals(
        _activity(ActivityKind.HIKING, date(2026, 3, 20)),
        period_start=period_start,
    )

    assert RECENT_WINDOW_DAYS == 28
    assert MIN_BASELINE_DAYS == 28
    assert signals.recency.nominal_window_days == 28
    assert signals.recency.effective_window_days == 14
    assert signals.recency.window_start == period_start
    assert signals.recency.baseline is None
    assert signals.recency.recent_to_baseline is None


def test_zero_baseline_denominators_produce_unavailable_ratios() -> None:
    activities = [
        *_activity(
            ActivityKind.RUNNING,
            PERIOD_START,
            moving_time=0,
            distance=0.0,
        ),
        *_activity(ActivityKind.RUNNING, date(2026, 3, 2)),
    ]

    ratios = _signals(activities).recency.recent_to_baseline

    assert ratios is not None
    assert ratios.activities_per_week_ratio == 2.0
    assert ratios.moving_time_seconds_per_week_ratio is None
    assert ratios.distance_meters_per_week_ratio is None


def test_inactivity_gaps_use_local_dates_and_include_boundaries() -> None:
    signals = _signals(
        [
            *_activity(ActivityKind.HIKING, date(2026, 1, 10)),
            *_activity(ActivityKind.HIKING, date(2026, 1, 20)),
            *_activity(ActivityKind.HIKING, date(2026, 3, 10)),
        ]
    )

    # Jan 21 through Mar 9 are the 48 inactive dates between activities.
    assert signals.longest_inactivity_gap_days == 48
    assert signals.days_since_last_activity == 19


def test_mixed_activity_kinds_have_independent_consistency() -> None:
    activities = _activity(ActivityKind.ROAD_CYCLING, PERIOD_START)
    activities.extend(
        activity
        for activity_date in _weekly_dates(PERIOD_START, 12)
        for activity in _activity(ActivityKind.HIKING, activity_date)
    )

    profile = _profile(activities)
    by_kind = {signal.activity_kind: signal for signal in profile.consistency_signals}

    assert by_kind[ActivityKind.HIKING].active_week_ratio == 1.0
    assert by_kind[ActivityKind.ROAD_CYCLING].active_week_ratio == pytest.approx(
        1 / 12
    )
    assert by_kind[ActivityKind.ROAD_CYCLING].recency.volume.activity_count == 0
    assert by_kind[ActivityKind.HIKING].recency.volume.activity_count == 4


def test_timezone_changes_local_week_and_gap_dates_deterministically() -> None:
    activities = [
        ActivityAnalysisRecord(
            activity_kind=ActivityKind.RUNNING,
            started_at=datetime(2026, 1, 12, 7, 30, tzinfo=UTC),
            distance_meters=1_000.0,
            moving_time_seconds=300,
        ),
        ActivityAnalysisRecord(
            activity_kind=ActivityKind.RUNNING,
            started_at=datetime(2026, 1, 12, 8, 30, tzinfo=UTC),
            distance_meters=1_000.0,
            moving_time_seconds=300,
        ),
    ]

    utc = _signals(
        activities,
        period_start=date(2026, 1, 5),
        period_end=date(2026, 1, 18),
    )
    vancouver = _signals(
        activities,
        period_start=date(2026, 1, 5),
        period_end=date(2026, 1, 18),
        timezone="America/Vancouver",
    )

    assert utc.active_week_ratio == 0.5
    assert utc.longest_inactivity_gap_days == 7
    assert vancouver.active_week_ratio == 1.0
    assert vancouver.longest_inactivity_gap_days == 6
    assert vancouver.days_since_last_activity == 6


def test_empty_and_unsupported_histories_have_no_fabricated_signals() -> None:
    assert _profile([]).consistency_signals == []
    assert _profile(
        _activity(None, date(2026, 2, 1))
    ).consistency_signals == []


def test_recent_signals_do_not_change_historical_capability_ranges() -> None:
    profile = _profile(
        [
            *_activity(
                ActivityKind.ROAD_CYCLING,
                PERIOD_START,
                moving_time=20_000,
                distance=200_000.0,
            ),
            *_activity(
                ActivityKind.ROAD_CYCLING,
                date(2026, 3, 20),
                moving_time=1_000,
                distance=10_000.0,
            ),
        ]
    )

    distance_range = profile.activity_summaries[0].capability_ranges.distance_meters
    assert distance_range.sample_size == 2
    assert distance_range.p90 == 181_000.0
    assert profile.consistency_signals[0].recency.volume.distance_meters == 10_000.0
