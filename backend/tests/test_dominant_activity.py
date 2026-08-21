from itertools import permutations

import pytest

from app.domain.activities import ActivityKind
from app.domain.athlete_profile import ActivityKindSummary
from app.services.athlete_profile import calculate_dominant_activity


def _summary(
    activity_kind: ActivityKind,
    *,
    moving_time: int,
    count: int,
    distance: float,
) -> ActivityKindSummary:
    return ActivityKindSummary(
        activity_kind=activity_kind,
        activity_count=count,
        total_distance_meters=distance,
        total_moving_time_seconds=moving_time,
        total_elevation_gain_meters=None,
        elevation_sample_count=0,
        active_weeks=1,
        median_distance_meters=distance / count,
        median_moving_time_seconds=moving_time / count,
        median_elevation_gain_meters=None,
    )


def test_moving_time_wins_over_higher_count_and_distance() -> None:
    running = _summary(
        ActivityKind.RUNNING, moving_time=2_000, count=1, distance=5_000.0
    )
    cycling = _summary(
        ActivityKind.ROAD_CYCLING,
        moving_time=1_999,
        count=10,
        distance=100_000.0,
    )

    result = calculate_dominant_activity([cycling, running])

    assert result is not None
    assert result.activity_kind is ActivityKind.RUNNING
    assert result.total_moving_time_seconds == 2_000
    assert result.activity_count == 1
    assert result.total_distance_meters == 5_000.0


def test_activity_count_breaks_equal_moving_time_tie() -> None:
    running = _summary(
        ActivityKind.RUNNING, moving_time=2_000, count=3, distance=5_000.0
    )
    cycling = _summary(
        ActivityKind.ROAD_CYCLING,
        moving_time=2_000,
        count=2,
        distance=100_000.0,
    )

    result = calculate_dominant_activity([cycling, running])

    assert result is not None
    assert result.activity_kind is ActivityKind.RUNNING


def test_distance_breaks_equal_moving_time_and_count_tie() -> None:
    hiking = _summary(
        ActivityKind.HIKING, moving_time=2_000, count=2, distance=8_000.0
    )
    running = _summary(
        ActivityKind.RUNNING, moving_time=2_000, count=2, distance=10_000.0
    )

    result = calculate_dominant_activity([hiking, running])

    assert result is not None
    assert result.activity_kind is ActivityKind.RUNNING


@pytest.mark.parametrize(
    "summaries",
    [
        (
            _summary(
                ActivityKind.RUNNING,
                moving_time=2_000,
                count=2,
                distance=10_000.0,
            ),
            _summary(
                ActivityKind.HIKING,
                moving_time=2_000,
                count=2,
                distance=10_000.0,
            ),
        ),
        (
            _summary(
                ActivityKind.HIKING,
                moving_time=2_000,
                count=2,
                distance=10_000.0,
            ),
            _summary(
                ActivityKind.RUNNING,
                moving_time=2_000,
                count=2,
                distance=10_000.0,
            ),
        ),
    ],
)
def test_exact_tie_uses_activity_kind_value_ascending(
    summaries: tuple[ActivityKindSummary, ActivityKindSummary],
) -> None:
    result = calculate_dominant_activity(summaries)

    assert result is not None
    assert result.activity_kind is ActivityKind.HIKING


def test_single_represented_category_is_dominant() -> None:
    running = _summary(
        ActivityKind.RUNNING, moving_time=2_000, count=2, distance=10_000.0
    )

    result = calculate_dominant_activity([running])

    assert result is not None
    assert result.activity_kind is ActivityKind.RUNNING
    assert result.moving_time_share == 1.0


def test_empty_summaries_have_no_dominant_activity() -> None:
    assert calculate_dominant_activity([]) is None


def test_mixed_history_is_independent_of_input_order() -> None:
    summaries = [
        _summary(
            ActivityKind.HIKING, moving_time=2_000, count=4, distance=8_000.0
        ),
        _summary(
            ActivityKind.ROAD_CYCLING,
            moving_time=3_000,
            count=2,
            distance=50_000.0,
        ),
        _summary(
            ActivityKind.RUNNING, moving_time=1_000, count=5, distance=20_000.0
        ),
    ]

    for ordered_summaries in permutations(summaries):
        result = calculate_dominant_activity(ordered_summaries)
        assert result is not None
        assert result.activity_kind is ActivityKind.ROAD_CYCLING


def test_moving_time_share_uses_all_represented_summaries() -> None:
    result = calculate_dominant_activity(
        [
            _summary(
                ActivityKind.ROAD_CYCLING,
                moving_time=6_100,
                count=2,
                distance=50_000.0,
            ),
            _summary(
                ActivityKind.RUNNING,
                moving_time=3_900,
                count=3,
                distance=20_000.0,
            ),
        ]
    )

    assert result is not None
    assert result.moving_time_share == pytest.approx(0.61)


def test_zero_total_moving_time_has_zero_share() -> None:
    result = calculate_dominant_activity(
        [
            _summary(
                ActivityKind.HIKING, moving_time=0, count=1, distance=5_000.0
            ),
            _summary(
                ActivityKind.RUNNING, moving_time=0, count=1, distance=4_000.0
            ),
        ]
    )

    assert result is not None
    assert result.activity_kind is ActivityKind.HIKING
    assert result.moving_time_share == 0.0
