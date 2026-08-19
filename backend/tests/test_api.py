from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_activity_types_are_stable() -> None:
    response = client.get("/api/v1/activity-types")
    assert response.status_code == 200
    assert response.json()[0] == {"value": "walking", "label": "Walking"}
    assert len(response.json()) == 10
