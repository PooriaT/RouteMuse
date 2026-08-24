import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.domain.planning_areas import BoundingBox, PlanningArea
from app.integrations.geospatial.errors import (
    GeocoderMalformedResponseError,
    GeocoderRateLimitError,
    GeocoderTemporaryError,
    GeocoderTimeoutError,
)

GEOCODING_URL = "https://api.openrouteservice.org/geocode/search"


class _Geometry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    coordinates: tuple[float, float]


class _Properties(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: str


class _Feature(BaseModel):
    model_config = ConfigDict(extra="ignore")
    geometry: _Geometry
    properties: _Properties
    bbox: tuple[float, float, float, float] | None = None


class _Geocoding(BaseModel):
    model_config = ConfigDict(extra="ignore")
    attribution: str


class _FeatureCollection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    features: list[_Feature]
    geocoding: _Geocoding


class OpenRouteServiceGeocodingProvider:
    """Translate OpenRouteService/Pelias responses into RouteMuse locations."""

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._client = client

    async def search(self, query: str, *, limit: int = 5) -> list[PlanningArea]:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.get(
                GEOCODING_URL,
                params={"api_key": self._api_key, "text": query, "size": limit},
            )
        except httpx.TimeoutException as exc:
            raise GeocoderTimeoutError from exc
        except httpx.RequestError as exc:
            raise GeocoderTemporaryError from exc
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code == 429:
            raise GeocoderRateLimitError
        if response.status_code >= 500:
            raise GeocoderTemporaryError
        if response.is_error:
            raise GeocoderTemporaryError

        try:
            payload = _FeatureCollection.model_validate(response.json())
            return [
                self._normalize(feature, payload.geocoding.attribution)
                for feature in payload.features
            ]
        except (ValueError, ValidationError, TypeError) as exc:
            raise GeocoderMalformedResponseError from exc

    @staticmethod
    def _normalize(feature: _Feature, attribution: str) -> PlanningArea:
        longitude, latitude = feature.geometry.coordinates
        bbox = feature.bbox
        bounding_box = (
            BoundingBox(south=bbox[1], west=bbox[0], north=bbox[3], east=bbox[2])
            if bbox is not None
            else None
        )
        return PlanningArea(
            latitude=latitude,
            longitude=longitude,
            display_name=feature.properties.label,
            bounding_box=bounding_box,
            source_provider="openrouteservice",
            source_attribution=attribution,
        )
