from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.activities import ActivityKind
from app.domain.athlete_profile import ActivityAnalysisRecord, RepresentativeRange
from app.services.athlete_profile import (
    calculate_activity_summaries,
    calculate_representative_range,
)


def _activity(
    activity_kind: ActivityKind,
    *,
    distance: float,
    moving_time: int,
    elevation: float | None,
    day: int = 1,
) -> ActivityAnalysisRecord:
    return ActivityAnalysisRecord(
        activity_kind=activity_kind,
        started_at=datetime(2026, 1, 1, 12, tzinfo=UTC)
        + timedelta(days=day - 1),
        distance_meters=distance,
        moving_time_seconds=moving_time,
        elevation_gain_meters=elevation,
    )


def _profile(activities: list[ActivityAnalysisRecord]):
    return calculate_activity_summaries(
        activities,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 2, 28),
        timezone="UTC",
    )


def _range_values(value_range: RepresentativeRange) -> tuple[float, ...]:
    return (
        value_range.p25,
        value_range.median,
        value_range.p75,
        value_range.p90,
    )


def test_distance_and_duration_ranges_use_exact_linear_percentiles() -> None:
    activities = [
        _activity(
            ActivityKind.RUNNING,
            distance=distance,
            moving_time=moving_time,
            elevation=100.0,
            day=index,
        )
        for index, (distance, moving_time) in enumerate(
            zip(
                [1_000.0, 2_000.0, 3_000.0, 4_000.0, 5_000.0],
                [100, 200, 300, 400, 500],
                strict=True,
            ),
            start=1,
        )
    ]

    ranges = _profile(activities).activity_summaries[0].capability_ranges

    assert ranges.distance_meters.sample_size == 5
    assert _range_values(ranges.distance_meters) == (
        2_000.0,
        3_000.0,
        4_000.0,
        4_600.0,
    )
    assert ranges.moving_time_seconds.sample_size == 5
    assert _range_values(ranges.moving_time_seconds) == (200.0, 300.0, 400.0, 460.0)


def test_elevation_excludes_missing_values_and_reports_metric_sample_size() -> None:
    activities = [
        _activity(
            ActivityKind.HIKING,
            distance=5_000.0,
            moving_time=3_000,
            elevation=elevation,
            day=index,
        )
        for index, elevation in enumerate([100.0, None, 300.0], start=1)
    ]

    elevation_range = (
        _profile(activities)
        .activity_summaries[0]
        .capability_ranges.elevation_gain_meters
    )

    assert elevation_range is not None
    assert elevation_range.sample_size == 2
    assert _range_values(elevation_range) == (150.0, 200.0, 250.0, 280.0)


def test_climbing_density_excludes_zero_distance_and_missing_elevation() -> None:
    summary = _profile(
        [
            _activity(
                ActivityKind.HIKING,
                distance=2_000.0,
                moving_time=1_200,
                elevation=100.0,
                day=1,
            ),
            _activity(
                ActivityKind.HIKING,
                distance=0.0,
                moving_time=300,
                elevation=80.0,
                day=2,
            ),
            _activity(
                ActivityKind.HIKING,
                distance=4_000.0,
                moving_time=2_400,
                elevation=None,
                day=3,
            ),
        ]
    ).activity_summaries[0]

    density_range = summary.capability_ranges.elevation_gain_meters_per_km
    assert density_range is not None
    assert density_range.sample_size == 1
    assert _range_values(density_range) == (50.0, 50.0, 50.0, 50.0)
    assert summary.capability_ranges.elevation_gain_meters is not None
    assert summary.capability_ranges.elevation_gain_meters.sample_size == 2


@pytest.mark.parametrize(
    "activity_kind",
    [
        ActivityKind.WALKING,
        ActivityKind.RUNNING,
        ActivityKind.TRAIL_RUNNING,
        ActivityKind.HIKING,
    ],
)
def test_foot_activity_kinds_expose_pace_seconds_per_km(
    activity_kind: ActivityKind,
) -> None:
    ranges = _profile(
        [
            _activity(
                activity_kind,
                distance=5_000.0,
                moving_time=1_500,
                elevation=50.0,
            )
        ]
    ).activity_summaries[0].capability_ranges

    assert ranges.pace_seconds_per_km is not None
    assert ranges.pace_seconds_per_km.median == 300.0
    assert ranges.average_moving_speed_meters_per_second is None


@pytest.mark.parametrize(
    "activity_kind",
    [
        ActivityKind.ROAD_CYCLING,
        ActivityKind.GRAVEL_CYCLING,
        ActivityKind.MOUNTAIN_BIKING,
        ActivityKind.ALPINE_SKIING,
        ActivityKind.BACKCOUNTRY_SKIING,
        ActivityKind.NORDIC_SKIING,
    ],
)
def test_cycling_and_ski_kinds_expose_average_moving_speed(
    activity_kind: ActivityKind,
) -> None:
    ranges = _profile(
        [
            _activity(
                activity_kind,
                distance=10_000.0,
                moving_time=2_000,
                elevation=50.0,
            )
        ]
    ).activity_summaries[0].capability_ranges

    assert ranges.average_moving_speed_meters_per_second is not None
    assert ranges.average_moving_speed_meters_per_second.median == 5.0
    assert ranges.pace_seconds_per_km is None


@pytest.mark.parametrize(
    "activity_kind", [ActivityKind.RUNNING, ActivityKind.ROAD_CYCLING]
)
def test_zero_distance_or_moving_time_cannot_produce_pace_or_speed(
    activity_kind: ActivityKind,
) -> None:
    ranges = _profile(
        [
            _activity(
                activity_kind,
                distance=0.0,
                moving_time=100,
                elevation=0.0,
                day=1,
            ),
            _activity(
                activity_kind,
                distance=1_000.0,
                moving_time=0,
                elevation=0.0,
                day=2,
            ),
        ]
    ).activity_summaries[0].capability_ranges

    assert ranges.pace_seconds_per_km is None
    assert ranges.average_moving_speed_meters_per_second is None


def test_single_massive_effort_does_not_define_representative_distance() -> None:
    typical_rides = [
        _activity(
            ActivityKind.ROAD_CYCLING,
            distance=50_000.0,
            moving_time=7_200,
            elevation=500.0,
            day=index,
        )
        for index in range(1, 46)
    ]
    outlier = _activity(
        ActivityKind.ROAD_CYCLING,
        distance=230_000.0,
        moving_time=30_000,
        elevation=2_000.0,
        day=46,
    )

    distance_range = (
        _profile([*typical_rides, outlier])
        .activity_summaries[0]
        .capability_ranges.distance_meters
    )

    assert distance_range.sample_size == 46
    assert distance_range.median == 50_000.0
    assert distance_range.p90 == 50_000.0
    assert distance_range.p90 != 230_000.0


def test_representative_range_sparse_behavior() -> None:
    assert calculate_representative_range([]) is None

    single = calculate_representative_range([12.0])
    assert single is not None
    assert single.sample_size == 1
    assert _range_values(single) == (12.0, 12.0, 12.0, 12.0)

    pair = calculate_representative_range([10.0, 20.0])
    assert pair is not None
    assert pair.sample_size == 2
    assert _range_values(pair) == (12.5, 15.0, 17.5, 19.0)


def test_capability_ranges_are_independent_per_activity_kind() -> None:
    profile = _profile(
        [
            _activity(
                ActivityKind.HIKING,
                distance=8_000.0,
                moving_time=3_600,
                elevation=500.0,
                day=1,
            ),
            _activity(
                ActivityKind.ROAD_CYCLING,
                distance=230_000.0,
                moving_time=30_000,
                elevation=2_000.0,
                day=2,
            ),
        ]
    )
    summaries = {
        summary.activity_kind: summary for summary in profile.activity_summaries
    }

    hiking_range = summaries[ActivityKind.HIKING].capability_ranges.distance_meters
    cycling_range = (
        summaries[ActivityKind.ROAD_CYCLING].capability_ranges.distance_meters
    )
    assert hiking_range.median == 8_000.0
    assert hiking_range.p90 == 8_000.0
    assert cycling_range.median == 230_000.0


def test_empty_profile_has_no_kind_or_metric_ranges() -> None:
    assert _profile([]).activity_summaries == []


def test_percentiles_are_independent_of_input_order() -> None:
    forward = calculate_representative_range([1.0, 2.0, 7.0, 10.0])
    reverse = calculate_representative_range([10.0, 7.0, 2.0, 1.0])

    assert forward == reverse
