from pydantic import TypeAdapter

from app.domain.activities import ActivityKind


def test_activity_kind_serialization() -> None:
    adapter = TypeAdapter(ActivityKind)
    assert adapter.dump_json(ActivityKind.TRAIL_RUNNING) == b'"trail_running"'
