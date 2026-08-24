from fastapi import APIRouter, HTTPException, Request

from app.domain.planning import RoutePlanningRequest
from app.domain.routes import CandidateGenerationResult
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
from app.services.route_candidates import (
    CandidateGenerationError,
    generate_route_candidates,
)

router = APIRouter(prefix="/route-candidates", tags=["route candidates"])


def _error(status: int, code: str, message: str, **metadata: int) -> HTTPException:
    detail: dict[str, str | int] = {"code": code, "message": message, **metadata}
    return HTTPException(status_code=status, detail=detail)


@router.post("", response_model=CandidateGenerationResult)
async def create_route_candidates(
    planning_request: RoutePlanningRequest, request: Request
) -> CandidateGenerationResult:
    """Generate ordered factual loops without ranking, persistence, or an LLM."""
    provider = OpenRouteServiceRoutingProvider(request.app.state.settings)
    try:
        return await generate_route_candidates(planning_request, provider)
    except CandidateGenerationError as exc:
        status = (
            422
            if exc.code
            in {
                "route_target_distance_required",
                "unsupported_generation_mode",
                "route_target_exceeds_provider_limit",
            }
            else 404
        )
        raise _error(status, exc.code, str(exc)) from exc
    except RouteProviderRateLimitError as exc:
        metadata = (
            {"retry_after_seconds": exc.retry_after_seconds}
            if exc.retry_after_seconds is not None
            else {}
        )
        raise _error(429, "route_provider_rate_limited", str(exc), **metadata) from exc
    except (ProviderConfigurationError, ProviderAuthenticationError) as exc:
        raise _error(503, "route_provider_unavailable", str(exc)) from exc
    except UnsupportedActivityError as exc:
        raise _error(422, "unsupported_activity", str(exc)) from exc
    except (ProviderInvalidRequestError, ProviderLimitError) as exc:
        raise _error(422, "route_provider_rejected_request", str(exc)) from exc
    except RouteProviderTimeoutError as exc:
        raise _error(504, "route_provider_timeout", str(exc)) from exc
    except RouteProviderTemporaryError as exc:
        raise _error(503, "route_provider_unavailable", str(exc)) from exc
    except RouteProviderMalformedResponseError as exc:
        raise _error(502, "route_provider_invalid_response", str(exc)) from exc
