from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.planning_areas import PlanningArea
from app.integrations.geospatial.errors import GeocoderRateLimitError
from app.integrations.geospatial.openrouteservice import (
    OpenRouteServiceGeocodingProvider,
)
from app.main import create_app


def test_missing_configuration_is_safe_and_does_not_break_health() -> None:
    client = TestClient(create_app(Settings(openrouteservice_api_key=None)))
    assert client.get("/health").status_code == 200
    response = client.get("/api/v1/planning-areas/search?q=Vancouver")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "geocoder_not_configured"


def test_query_and_limit_validation() -> None:
    client = TestClient(create_app(Settings(openrouteservice_api_key="secret")))
    for url in [
        "/api/v1/planning-areas/search?q=x",
        "/api/v1/planning-areas/search?q=%20%20",
        "/api/v1/planning-areas/search?q=valid&limit=11",
    ]:
        assert client.get(url).status_code == 422


def test_api_returns_normalized_results_without_key(monkeypatch: object) -> None:
    async def search(self: object, query: str, *, limit: int = 5) -> list[PlanningArea]:
        assert query == "Vancouver"
        return [
            PlanningArea(
                latitude=49.2,
                longitude=-123.1,
                display_name="Vancouver, BC",
                source_provider="openrouteservice",
                source_attribution="© provider",
            )
        ]

    monkeypatch.setattr(OpenRouteServiceGeocodingProvider, "search", search)  # type: ignore[attr-defined]
    client = TestClient(
        create_app(Settings(openrouteservice_api_key="super-secret-key"))
    )
    response = client.get("/api/v1/planning-areas/search?q=Vancouver")
    assert response.status_code == 200
    assert response.json()[0]["display_name"] == "Vancouver, BC"
    assert "super-secret-key" not in response.text


def test_rate_limit_is_safe(monkeypatch: object) -> None:
    async def search(self: object, query: str, *, limit: int = 5) -> list[PlanningArea]:
        raise GeocoderRateLimitError

    monkeypatch.setattr(OpenRouteServiceGeocodingProvider, "search", search)  # type: ignore[attr-defined]
    client = TestClient(
        create_app(Settings(openrouteservice_api_key="super-secret-key"))
    )
    response = client.get("/api/v1/planning-areas/search?q=Vancouver")
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "geocoder_rate_limited"
    assert "super-secret-key" not in response.text
