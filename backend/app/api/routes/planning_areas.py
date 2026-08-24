from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.domain.planning_areas import PlanningArea
from app.integrations.geospatial.errors import (
    GeocoderMalformedResponseError,
    GeocoderNotConfiguredError,
    GeocoderRateLimitError,
    GeocoderTemporaryError,
    GeocoderTimeoutError,
)
from app.integrations.geospatial.openrouteservice import (
    OpenRouteServiceGeocodingProvider,
)

router = APIRouter(prefix="/planning-areas", tags=["planning areas"])


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@router.get("/search", response_model=list[PlanningArea])
async def search_planning_areas(
    request: Request,
    q: Annotated[str, Query(min_length=2, max_length=120)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> list[PlanningArea]:
    query = q.strip()
    if len(query) < 2:
        raise _error(
            422, "invalid_query", "Search query must contain at least 2 characters."
        )
    secret = request.app.state.settings.openrouteservice_api_key
    if secret is None or not secret.get_secret_value().strip():
        error = GeocoderNotConfiguredError()
        raise _error(
            503, "geocoder_not_configured", "Location search is not configured."
        ) from error
    provider = OpenRouteServiceGeocodingProvider(secret.get_secret_value())
    try:
        return await provider.search(query, limit=limit)
    except GeocoderTimeoutError as exc:
        raise _error(504, "geocoder_timeout", "Location search timed out.") from exc
    except GeocoderRateLimitError as exc:
        raise _error(
            429, "geocoder_rate_limited", "Location search is temporarily rate limited."
        ) from exc
    except GeocoderTemporaryError as exc:
        raise _error(
            503, "geocoder_unavailable", "Location search is temporarily unavailable."
        ) from exc
    except GeocoderMalformedResponseError as exc:
        raise _error(
            502,
            "geocoder_invalid_response",
            "Location provider returned an invalid response.",
        ) from exc
