from fastapi.testclient import TestClient

from app.main import app, create_app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_activity_types_are_stable() -> None:
    response = client.get("/api/v1/activity-types")
    assert response.status_code == 200
    assert response.json() == [
        {"value": "walking", "label": "Walking"},
        {"value": "running", "label": "Running"},
        {"value": "trail_running", "label": "Trail Running"},
        {"value": "hiking", "label": "Hiking"},
        {"value": "road_cycling", "label": "Road Cycling"},
        {"value": "gravel_cycling", "label": "Gravel Cycling"},
        {"value": "mountain_biking", "label": "Mountain Biking"},
        {"value": "alpine_skiing", "label": "Alpine Skiing"},
        {"value": "backcountry_skiing", "label": "Backcountry Skiing"},
        {"value": "nordic_skiing", "label": "Nordic Skiing"},
    ]


def test_application_starts_without_external_services() -> None:
    with TestClient(create_app()) as application_client:
        assert application_client.get("/health").status_code == 200
