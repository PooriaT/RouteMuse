import math

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domain.activities import ActivityKind
from app.domain.planning import (
    DesiredChallenge,
    NoveltyPreference,
    RoutePlanningRequest,
)
from app.domain.routes import RouteShape
from app.main import create_app


def planning_area() -> dict[str, object]:
    return {
        "latitude": 49.2827,
        "longitude": -123.1207,
        "display_name": "Vancouver, BC",
        "bounding_box": {
            "south": 49.19,
            "west": -123.27,
            "north": 49.32,
            "east": -122.99,
        },
        "source_provider": "openrouteservice",
        "source_attribution": "© OpenStreetMap contributors",
    }


def minimal_payload() -> dict[str, object]:
    return {"planning_area": planning_area(), "activity_kind": "road_cycling"}


def test_minimal_request_keeps_all_overrides_optional() -> None:
    request = RoutePlanningRequest.model_validate(minimal_payload())

    assert request.activity_kind is ActivityKind.ROAD_CYCLING
    assert request.target_distance_meters is None
    assert request.target_duration_seconds is None
    assert request.desired_challenge is None
    assert request.route_shape is None
    assert request.novelty_preference is None


def test_full_request_uses_canonical_units_and_preferences() -> None:
    request = RoutePlanningRequest.model_validate(
        {
            **minimal_payload(),
            "target_distance_meters": 42195.5,
            "target_duration_seconds": 10800,
            "desired_challenge": "hard",
            "route_shape": "point_to_point",
            "novelty_preference": "novel",
        }
    )

    assert request.target_distance_meters == 42195.5
    assert request.target_duration_seconds == 10800
    assert request.desired_challenge is DesiredChallenge.HARD
    assert request.route_shape is RouteShape.POINT_TO_POINT
    assert request.novelty_preference is NoveltyPreference.NOVEL


@pytest.mark.parametrize("activity_kind", list(ActivityKind))
def test_each_activity_kind_is_supported(activity_kind: ActivityKind) -> None:
    request = RoutePlanningRequest.model_validate(
        {**minimal_payload(), "activity_kind": activity_kind.value}
    )
    assert request.activity_kind is activity_kind


@pytest.mark.parametrize("route_shape", list(RouteShape))
def test_each_route_shape_is_supported(route_shape: RouteShape) -> None:
    request = RoutePlanningRequest.model_validate(
        {**minimal_payload(), "route_shape": route_shape.value}
    )
    assert request.route_shape is route_shape


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("planning_area", "latitude"), 91),
        (("planning_area", "longitude"), -181),
        (("planning_area", "bounding_box", "south"), 50),
        (("target_distance_meters",), 0),
        (("target_distance_meters",), -1),
        (("target_distance_meters",), math.nan),
        (("target_distance_meters",), math.inf),
        (("target_distance_meters",), True),
        (("target_duration_seconds",), 0),
        (("target_duration_seconds",), -1),
        (("target_duration_seconds",), True),
        (("activity_kind",), "swimming"),
        (("route_shape",), "triangle"),
        (("desired_challenge",), "extreme"),
        (("novelty_preference",), "surprise_me"),
    ],
)
def test_invalid_request_values_are_rejected(
    path: tuple[str, ...], value: object
) -> None:
    payload = minimal_payload()
    target = payload
    for part in path[:-1]:
        target = target[part]  # type: ignore[assignment,index]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        RoutePlanningRequest.model_validate(payload)


def test_unknown_planning_request_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        RoutePlanningRequest.model_validate(
            {**minimal_payload(), "target_distnace_meters": 10_000}
        )


def test_unusual_distance_duration_combination_is_allowed() -> None:
    request = RoutePlanningRequest.model_validate(
        {
            **minimal_payload(),
            "target_distance_meters": 1_000_000,
            "target_duration_seconds": 1,
        }
    )
    assert request.target_distance_meters == 1_000_000
    assert request.target_duration_seconds == 1


def test_validate_endpoint_echoes_normalized_request_without_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_call(*args: object, **kwargs: object) -> None:
        pytest.fail("planning validation must not contact a provider")

    monkeypatch.setattr(
        "app.integrations.geospatial.openrouteservice."
        "OpenRouteServiceGeocodingProvider.search",
        unexpected_call,
    )
    client = TestClient(create_app())
    response = client.post("/api/v1/planning/validate", json=minimal_payload())

    assert response.status_code == 200
    assert response.json() == {
        **minimal_payload(),
        "target_distance_meters": None,
        "target_duration_seconds": None,
        "desired_challenge": None,
        "route_shape": None,
        "novelty_preference": None,
    }


@pytest.mark.parametrize(
    "invalid_override",
    [
        {"target_distance_meters": 0},
        {"target_distance_meters": True},
        {"target_duration_seconds": True},
        {"target_distnace_meters": 10_000},
    ],
)
def test_validate_endpoint_rejects_invalid_request(
    invalid_override: dict[str, object],
) -> None:
    response = TestClient(create_app()).post(
        "/api/v1/planning/validate",
        json={**minimal_payload(), **invalid_override},
    )
    assert response.status_code == 422
