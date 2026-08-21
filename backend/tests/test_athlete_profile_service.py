from datetime import UTC, date, datetime

import pytest

from app.domain.activities import ActivityKind
from app.domain.athlete_profile import ActivityAnalysisRecord, ActivityKindSummary
from app.services.athlete_profile import calculate_activity_summaries


def _activity(
    activity_kind: ActivityKind | None,
    started_at: datetime,
    *,
    distance: float = 1_000.0,
    moving_time: int = 600,
    elevation: float | None = 25.0,
) -> ActivityAnalysisRecord:
    return ActivityAnalysisRecord(
        activity_kind=activity_kind,
        started_at=started_at,
        distance_meters=distance,
        moving_time_seconds=moving_time,
        elevation_gain_meters=elevation,
    )


def _calculate(
    activities: list[ActivityAnalysisRecord],
    *,
    timezone: str = "UTC",
):
    return calculate_activity_summaries(
        activities,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        timezone=timezone,
    )


def _only_summary(
    activities: list[ActivityAnalysisRecord],
    *,
    timezone: str = "UTC",
) -> ActivityKindSummary:
    profile = _calculate(activities, timezone=timezone)
    assert len(profile.activity_summaries) == 1
    return profile.activity_summaries[0]


def test_single_activity_kind_calculates_all_summary_metrics() -> None:
    summary = _only_summary(
        [
            _activity(
                ActivityKind.RUNNING,
                datetime(2026, 1, 6, 12, tzinfo=UTC),
                distance=5_000.0,
                moving_time=1_500,
                elevation=80.0,
            ),
            _activity(
                ActivityKind.RUNNING,
                datetime(2026, 1, 8, 12, tzinfo=UTC),
                distance=7_000.0,
                moving_time=2_100,
                elevation=120.0,
            ),
        ]
    )

    assert summary.activity_kind is ActivityKind.RUNNING
    assert summary.activity_count == 2
    assert summary.total_distance_meters == 12_000.0
    assert summary.total_moving_time_seconds == 3_600
    assert summary.total_elevation_gain_meters == 200.0
    assert summary.elevation_sample_count == 2
    assert summary.active_weeks == 1
    assert summary.median_distance_meters == 6_000.0
    assert summary.median_moving_time_seconds == 1_800.0
    assert summary.median_elevation_gain_meters == 100.0


def test_mixed_activity_kinds_are_summarized_independently() -> None:
    profile = _calculate(
        [
            _activity(
                ActivityKind.ROAD_CYCLING,
                datetime(2026, 1, 3, 12, tzinfo=UTC),
                distance=40_000.0,
            ),
            _activity(
                ActivityKind.ROAD_CYCLING,
                datetime(2026, 1, 10, 12, tzinfo=UTC),
                distance=60_000.0,
            ),
            _activity(
                ActivityKind.HIKING,
                datetime(2026, 1, 4, 12, tzinfo=UTC),
                distance=8_000.0,
            ),
            _activity(
                ActivityKind.RUNNING,
                datetime(2026, 1, 5, 12, tzinfo=UTC),
                distance=5_000.0,
            ),
        ]
    )

    summaries = {
        summary.activity_kind: summary for summary in profile.activity_summaries
    }
    assert profile.activities_analyzed == 4
    assert set(summaries) == {
        ActivityKind.HIKING,
        ActivityKind.ROAD_CYCLING,
        ActivityKind.RUNNING,
    }
    assert summaries[ActivityKind.ROAD_CYCLING].activity_count == 2
    assert summaries[ActivityKind.ROAD_CYCLING].median_distance_meters == 50_000.0
    assert summaries[ActivityKind.HIKING].activity_count == 1
    assert summaries[ActivityKind.HIKING].median_distance_meters == 8_000.0
    assert summaries[ActivityKind.RUNNING].total_distance_meters == 5_000.0


def test_zero_activities_returns_an_empty_typed_profile() -> None:
    profile = _calculate([])

    assert profile.activities_analyzed == 0
    assert profile.unsupported_activities_excluded == 0
    assert profile.activity_summaries == []


def test_one_activity_uses_its_values_as_medians() -> None:
    summary = _only_summary(
        [
            _activity(
                ActivityKind.HIKING,
                datetime(2026, 1, 2, 12, tzinfo=UTC),
                distance=0.0,
                moving_time=0,
                elevation=0.0,
            )
        ]
    )

    assert summary.activity_count == 1
    assert summary.median_distance_meters == 0.0
    assert summary.median_moving_time_seconds == 0.0
    assert summary.median_elevation_gain_meters == 0.0


def test_two_activities_use_the_mean_of_middle_values_as_medians() -> None:
    summary = _only_summary(
        [
            _activity(
                ActivityKind.HIKING,
                datetime(2026, 1, 2, 12, tzinfo=UTC),
                distance=1_000.0,
                moving_time=100,
                elevation=10.0,
            ),
            _activity(
                ActivityKind.HIKING,
                datetime(2026, 1, 3, 12, tzinfo=UTC),
                distance=2_000.0,
                moving_time=201,
                elevation=21.0,
            ),
        ]
    )

    assert summary.median_distance_meters == 1_500.0
    assert summary.median_moving_time_seconds == 150.5
    assert summary.median_elevation_gain_meters == 15.5


def test_partial_elevation_uses_only_known_samples() -> None:
    summary = _only_summary(
        [
            _activity(
                ActivityKind.MOUNTAIN_BIKING,
                datetime(2026, 1, 2, 12, tzinfo=UTC),
                elevation=100.0,
            ),
            _activity(
                ActivityKind.MOUNTAIN_BIKING,
                datetime(2026, 1, 3, 12, tzinfo=UTC),
                elevation=None,
            ),
            _activity(
                ActivityKind.MOUNTAIN_BIKING,
                datetime(2026, 1, 4, 12, tzinfo=UTC),
                elevation=300.0,
            ),
        ]
    )

    assert summary.activity_count == 3
    assert summary.elevation_sample_count == 2
    assert summary.total_elevation_gain_meters == 400.0
    assert summary.median_elevation_gain_meters == 200.0


def test_all_missing_elevation_produces_no_elevation_aggregates() -> None:
    summary = _only_summary(
        [
            _activity(
                ActivityKind.WALKING,
                datetime(2026, 1, 2, 12, tzinfo=UTC),
                elevation=None,
            ),
            _activity(
                ActivityKind.WALKING,
                datetime(2026, 1, 3, 12, tzinfo=UTC),
                elevation=None,
            ),
        ]
    )

    assert summary.elevation_sample_count == 0
    assert summary.total_elevation_gain_meters is None
    assert summary.median_elevation_gain_meters is None


def test_active_weeks_count_distinct_monday_based_local_weeks() -> None:
    summary = _only_summary(
        [
            _activity(
                ActivityKind.RUNNING,
                datetime(2026, 1, 5, 12, tzinfo=UTC),
            ),
            _activity(
                ActivityKind.RUNNING,
                datetime(2026, 1, 11, 12, tzinfo=UTC),
            ),
            _activity(
                ActivityKind.RUNNING,
                datetime(2026, 1, 12, 12, tzinfo=UTC),
            ),
        ]
    )

    assert summary.active_weeks == 2


def test_timezone_conversion_changes_week_bucket_near_local_boundary() -> None:
    activities = [
        _activity(
            ActivityKind.RUNNING,
            datetime(2026, 1, 5, 0, 30, tzinfo=UTC),
        ),
        _activity(
            ActivityKind.RUNNING,
            datetime(2026, 1, 11, 23, 30, tzinfo=UTC),
        ),
    ]

    assert _only_summary(activities, timezone="UTC").active_weeks == 1
    assert _only_summary(activities, timezone="America/Vancouver").active_weeks == 2


def test_unsupported_activities_are_counted_but_never_summarized() -> None:
    profile = _calculate(
        [
            _activity(
                ActivityKind.RUNNING,
                datetime(2026, 1, 5, 12, tzinfo=UTC),
                distance=5_000.0,
            ),
            _activity(
                None,
                datetime(2026, 1, 5, 13, tzinfo=UTC),
                distance=100_000.0,
                moving_time=50_000,
                elevation=5_000.0,
            ),
        ]
    )

    assert profile.activities_analyzed == 1
    assert profile.unsupported_activities_excluded == 1
    assert profile.activity_summaries[0].total_distance_meters == 5_000.0


def test_period_with_only_unsupported_activities_is_safe() -> None:
    profile = _calculate([_activity(None, datetime(2026, 1, 5, 12, tzinfo=UTC))])

    assert profile.activities_analyzed == 0
    assert profile.unsupported_activities_excluded == 1
    assert profile.activity_summaries == []


def test_activities_outside_selected_local_period_are_excluded() -> None:
    profile = calculate_activity_summaries(
        [
            _activity(
                ActivityKind.RUNNING,
                datetime(2026, 1, 1, 7, 59, tzinfo=UTC),
            ),
            _activity(
                ActivityKind.RUNNING,
                datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
            ),
            _activity(None, datetime(2026, 1, 2, 8, 0, tzinfo=UTC)),
        ],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 1),
        timezone="America/Vancouver",
    )

    assert profile.activities_analyzed == 1
    assert profile.unsupported_activities_excluded == 0


@pytest.mark.parametrize(
    ("period_start", "period_end", "message"),
    [
        (date(2026, 1, 2), date(2026, 1, 1), "period_start"),
        (date.max, date.max, "period_end"),
    ],
)
def test_invalid_period_is_rejected(
    period_start: date, period_end: date, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        calculate_activity_summaries(
            [],
            period_start=period_start,
            period_end=period_end,
            timezone="UTC",
        )


@pytest.mark.parametrize(
    "timezone",
    ["localtime", "posixrules", "posix/UTC", "right/UTC"],
)
def test_system_dependent_timezone_keys_are_rejected(timezone: str) -> None:
    with pytest.raises(ValueError, match="valid IANA timezone"):
        calculate_activity_summaries(
            [],
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            timezone=timezone,
        )
