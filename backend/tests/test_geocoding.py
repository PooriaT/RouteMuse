import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.domain.planning_areas import BoundingBox, PlanningArea
from app.integrations.geospatial.errors import (
    GeocoderMalformedResponseError,
    GeocoderRateLimitError,
    GeocoderTemporaryError,
    GeocoderTimeoutError,
)
from app.integrations.geospatial.openrouteservice import (
    OpenRouteServiceGeocodingProvider,
)


def sync_test(
    function: Callable[..., Coroutine[Any, Any, None]],
) -> Callable[..., None]:
    @wraps(function)
    def wrapper(*args: object, **kwargs: object) -> None:
        asyncio.run(function(*args, **kwargs))

    return wrapper


def response(payload: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


def payload(features: list[dict[str, object]]) -> dict[str, object]:
    return {
        "features": features,
        "geocoding": {"attribution": "© openrouteservice.org | © OpenStreetMap"},
    }


def feature(
    label: str, coordinates: list[float], bbox: list[float] | None = None
) -> dict[str, object]:
    value: dict[str, object] = {
        "geometry": {"coordinates": coordinates},
        "properties": {"label": label},
    }
    if bbox is not None:
        value["bbox"] = bbox
    return value


@sync_test
async def test_maps_multiple_results_and_optional_bounds() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["api_key"] == "secret"
        assert request.url.params["text"] == "North Vancouver"
        assert request.url.params["size"] == "2"
        return response(
            payload(
                [
                    feature(
                        "North Vancouver, BC",
                        [-123.07, 49.32],
                        [-123.2, 49.2, -122.9, 49.4],
                    ),
                    feature("North Vancouver District, BC", [-123.02, 49.36]),
                ]
            )
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        areas = await OpenRouteServiceGeocodingProvider("secret", client).search(
            "North Vancouver", limit=2
        )

    assert areas == [
        PlanningArea(
            latitude=49.32,
            longitude=-123.07,
            display_name="North Vancouver, BC",
            bounding_box=BoundingBox(south=49.2, west=-123.2, north=49.4, east=-122.9),
            source_provider="openrouteservice",
            source_attribution="© openrouteservice.org | © OpenStreetMap",
        ),
        PlanningArea(
            latitude=49.36,
            longitude=-123.02,
            display_name="North Vancouver District, BC",
            bounding_box=None,
            source_provider="openrouteservice",
            source_attribution="© openrouteservice.org | © OpenStreetMap",
        ),
    ]


@sync_test
async def test_empty_results_are_successful() -> None:
    transport = httpx.MockTransport(lambda _: response(payload([])))
    async with httpx.AsyncClient(transport=transport) as client:
        assert (
            await OpenRouteServiceGeocodingProvider("secret", client).search("Nowhere")
            == []
        )


@sync_test
@pytest.mark.parametrize(
    "bad_feature",
    [feature("Bad", [181, 49]), feature("Bad", [-123, 91]), {"unexpected": True}],
)
async def test_invalid_provider_payload_is_rejected(
    bad_feature: dict[str, object],
) -> None:
    transport = httpx.MockTransport(lambda _: response(payload([bad_feature])))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(GeocoderMalformedResponseError):
            await OpenRouteServiceGeocodingProvider("secret", client).search("Bad")


@sync_test
@pytest.mark.parametrize(
    ("handler", "error"),
    [
        (
            lambda request: (_ for _ in ()).throw(
                httpx.ReadTimeout("slow", request=request)
            ),
            GeocoderTimeoutError,
        ),
        (lambda _: response({}, 429), GeocoderRateLimitError),
        (lambda _: response({}, 503), GeocoderTemporaryError),
    ],
)
async def test_provider_failures_are_distinct(
    handler: object, error: type[Exception]
) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:  # type: ignore[arg-type]
        with pytest.raises(error):
            await OpenRouteServiceGeocodingProvider("secret", client).search("Place")


def test_domain_validates_coordinates_and_bounds() -> None:
    with pytest.raises(ValidationError):
        PlanningArea(
            latitude=91,
            longitude=0,
            display_name="Bad",
            source_provider="x",
            source_attribution="x",
        )
    with pytest.raises(ValidationError):
        BoundingBox(south=20, west=0, north=10, east=1)
