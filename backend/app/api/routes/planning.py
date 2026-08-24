from fastapi import APIRouter

from app.domain.planning import RoutePlanningRequest

router = APIRouter(prefix="/planning", tags=["planning"])


@router.post("/validate", response_model=RoutePlanningRequest)
async def validate_planning_request(
    planning_request: RoutePlanningRequest,
) -> RoutePlanningRequest:
    """Return a canonical request after schema validation, without side effects."""

    return planning_request
