from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.repositories.athlete_profile import AthleteProfileRepository
from app.db.repositories.strava import StravaSynchronizationRepository
from app.db.session import get_db_session
from app.domain.recommendations import RecommendationRequest, RecommendationResult
from app.integrations.contracts import RouteDiscoveryProvider
from app.integrations.llm.ollama import OllamaLlmProvider
from app.integrations.routing.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderInvalidRequestError,
    ProviderLimitError,
    RouteProviderMalformedResponseError,
    RouteProviderRateLimitError,
    RouteProviderTemporaryError,
    RouteProviderTimeoutError,
    UnsupportedActivityError,
)
from app.integrations.routing.openrouteservice import OpenRouteServiceRoutingProvider
from app.services.recommendations import RecommendationError, build_recommendations
from app.services.route_candidates import CandidateGenerationError
from app.services.route_difficulty import UnsupportedDifficultyScoringError
from app.services.route_excitement import UnsupportedExcitementScoringError

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def get_repositories(
    session: Annotated[Session, Depends(get_db_session)],
) -> tuple[AthleteProfileRepository, StravaSynchronizationRepository]:
    return AthleteProfileRepository(session), StravaSynchronizationRepository(session)


def get_discovery_provider(request: Request) -> RouteDiscoveryProvider:
    """Reuse the application's cache and concurrency guard across requests."""
    return request.app.state.overpass_discovery_provider


def error(status_code: int, code: str, message: str, **metadata: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, **metadata},
    )


@router.post("", response_model=RecommendationResult)
async def create_recommendations(
    body: RecommendationRequest,
    request: Request,
    repositories: Annotated[
        tuple[AthleteProfileRepository, StravaSynchronizationRepository],
        Depends(get_repositories),
    ],
    discovery: Annotated[RouteDiscoveryProvider, Depends(get_discovery_provider)],
) -> RecommendationResult:
    """Rank factual candidates, then add optional resilient reasoning."""
    routing = OpenRouteServiceRoutingProvider(request.app.state.settings)
    settings = request.app.state.settings
    llm = (
        OllamaLlmProvider(settings)
        if settings.ollama_base_url and settings.ollama_model
        else None
    )
    try:
        return await build_recommendations(
            body,
            repositories[0],
            repositories[1],
            routing,
            discovery,
            llm,
            llm_model=settings.ollama_model,
        )
    except RecommendationError as exc:
        conflict = {
            "strava_connection_required",
            "athlete_profile_history_incomplete",
        }
        raise error(409 if exc.code in conflict else 422, exc.code, str(exc)) from exc
    except CandidateGenerationError as exc:
        raise error(
            404 if exc.code == "no_route_candidates" else 422, exc.code, str(exc)
        ) from exc
    except RouteProviderRateLimitError as exc:
        metadata = (
            {"retry_after_seconds": exc.retry_after_seconds}
            if exc.retry_after_seconds is not None
            else {}
        )
        raise error(429, "route_provider_rate_limited", str(exc), **metadata) from exc
    except (ProviderConfigurationError, ProviderAuthenticationError) as exc:
        raise error(503, "route_provider_unavailable", str(exc)) from exc
    except UnsupportedActivityError as exc:
        raise error(422, "unsupported_activity", str(exc)) from exc
    except (
        UnsupportedDifficultyScoringError,
        UnsupportedExcitementScoringError,
    ) as exc:
        raise error(422, "unsupported_activity", str(exc)) from exc
    except (ProviderInvalidRequestError, ProviderLimitError) as exc:
        raise error(422, "route_provider_rejected_request", str(exc)) from exc
    except RouteProviderTimeoutError as exc:
        raise error(504, "route_provider_timeout", str(exc)) from exc
    except RouteProviderTemporaryError as exc:
        raise error(503, "route_provider_unavailable", str(exc)) from exc
    except RouteProviderMalformedResponseError as exc:
        raise error(502, "route_provider_invalid_response", str(exc)) from exc
    except SQLAlchemyError as exc:
        raise error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "athlete_profile_unavailable",
            "The saved activity history is temporarily unavailable.",
        ) from exc
