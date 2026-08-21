import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.activities import ActivityKind
from app.integrations.strava.dtos import StravaActivityDTO
from app.integrations.strava.normalization import (
    STRAVA_SPORT_TYPE_TO_ACTIVITY_KIND,
    normalize_strava_activity,
    normalize_strava_sport_type,
)

SUPPORTED_SPORT_TYPES = [
    ("Walk", ActivityKind.WALKING),
    ("Run", ActivityKind.RUNNING),
    ("TrailRun", ActivityKind.TRAIL_RUNNING),
    ("Hike", ActivityKind.HIKING),
    ("Ride", ActivityKind.ROAD_CYCLING),
    ("GravelRide", ActivityKind.GRAVEL_CYCLING),
    ("MountainBikeRide", ActivityKind.MOUNTAIN_BIKING),
    ("AlpineSki", ActivityKind.ALPINE_SKIING),
    ("BackcountrySki", ActivityKind.BACKCOUNTRY_SKIING),
    ("NordicSki", ActivityKind.NORDIC_SKIING),
]

UNSUPPORTED_SPORT_TYPES = [
    "VirtualRide",
    "EBikeRide",
    "EMountainBikeRide",
    "VirtualRun",
    "Snowboard",
    "Snowshoe",
    "RollerSki",
    "RockClimbing",
    "Rowing",
    "Swim",
    "Yoga",
    "Workout",
    "SomeFutureStravaSport",
]


@pytest.mark.parametrize(("source_sport_type", "expected_kind"), SUPPORTED_SPORT_TYPES)
def test_supported_sport_type_has_one_explicit_mapping(
    source_sport_type: str, expected_kind: ActivityKind
) -> None:
    result = normalize_strava_sport_type(source_sport_type)

    assert result.source_sport_type == source_sport_type
    assert result.activity_kind is expected_kind


def test_mapping_table_contains_only_the_supported_product_decisions() -> None:
    assert STRAVA_SPORT_TYPE_TO_ACTIVITY_KIND == dict(SUPPORTED_SPORT_TYPES)


@pytest.mark.parametrize("source_sport_type", UNSUPPORTED_SPORT_TYPES)
def test_unsupported_sport_type_remains_identifiable(
    source_sport_type: str,
) -> None:
    result = normalize_strava_sport_type(source_sport_type)

    assert result.source_sport_type == source_sport_type
    assert result.activity_kind is None


def test_sport_type_is_used_when_legacy_type_is_also_present() -> None:
    dto = StravaActivityDTO.model_validate(
        _activity_payload(sport_type="TrailRun", type="Ride")
    )

    result = normalize_strava_activity(dto)

    assert result.source_sport_type == "TrailRun"
    assert result.activity_kind is ActivityKind.TRAIL_RUNNING
    assert result.activity is not None
    assert result.activity.kind is ActivityKind.TRAIL_RUNNING


def test_legacy_type_alone_is_not_a_classification_contract() -> None:
    payload = _activity_payload(sport_type="Run")
    del payload["sport_type"]
    payload["type"] = "Run"

    with pytest.raises(ValidationError):
        StravaActivityDTO.model_validate(payload)


def test_supported_activity_is_converted_without_changing_canonical_units() -> None:
    dto = StravaActivityDTO.model_validate(_activity_payload(sport_type="Hike"))

    result = normalize_strava_activity(dto)

    assert result.source_sport_type == "Hike"
    assert result.activity_kind is ActivityKind.HIKING
    assert result.activity is not None
    assert result.activity.external_id == "9876543210"
    assert result.activity.kind is ActivityKind.HIKING
    assert result.activity.started_at == datetime(2026, 8, 20, 14, 30, tzinfo=UTC)
    assert result.activity.moving_time_seconds == 3_601
    assert result.activity.distance_meters == 12_345.6
    assert result.activity.elevation_gain_meters == 789.1


@pytest.mark.parametrize("source_sport_type", UNSUPPORTED_SPORT_TYPES)
def test_unsupported_activity_does_not_construct_a_domain_activity(
    source_sport_type: str,
) -> None:
    dto = StravaActivityDTO.model_validate(
        _activity_payload(sport_type=source_sport_type)
    )

    result = normalize_strava_activity(dto)

    assert result.source_sport_type == source_sport_type
    assert result.activity_kind is None
    assert result.activity is None


def test_domain_does_not_import_the_strava_integration() -> None:
    domain_path = Path(__file__).parents[1] / "app" / "domain"

    for source_path in domain_path.rglob("*.py"):
        tree = ast.parse(source_path.read_text(), filename=str(source_path))
        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)
                imported_modules.update(
                    f"{node.module}.{alias.name}" for alias in node.names
                )

        assert not any(
            module == "app.integrations.strava"
            or module.startswith("app.integrations.strava.")
            or module == "integrations.strava"
            or module.startswith("integrations.strava.")
            for module in imported_modules
        ), f"{source_path} imports the Strava integration"


def _activity_payload(*, sport_type: str, **extra: object) -> dict[str, object]:
    return {
        "id": 9_876_543_210,
        "sport_type": sport_type,
        "start_date": "2026-08-20T14:30:00Z",
        "moving_time": 3_601,
        "distance": 12_345.6,
        "total_elevation_gain": 789.1,
        "name": "Provider field outside the import contract",
        **extra,
    }
