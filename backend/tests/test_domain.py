from pydantic import TypeAdapter

from app.domain.activities import ActivityKind


def test_activity_kind_serialization() -> None:
    adapter = TypeAdapter(ActivityKind)
    assert adapter.dump_json(ActivityKind.TRAIL_RUNNING) == b'"trail_running"'


def test_activity_kind_values_are_the_routemuse_taxonomy() -> None:
    assert [kind.value for kind in ActivityKind] == [
        "walking",
        "running",
        "trail_running",
        "hiking",
        "road_cycling",
        "gravel_cycling",
        "mountain_biking",
        "alpine_skiing",
        "backcountry_skiing",
        "nordic_skiing",
    ]
