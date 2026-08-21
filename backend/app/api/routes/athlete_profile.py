from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.schemas.calendar import CalendarPeriodRequest
from app.db.repositories.athlete_profile import AthleteProfileRepository
from app.db.session import get_db_session
from app.domain.athlete_profile import AthleteProfile
from app.domain.calendar import calendar_period_bounds
from app.services.athlete_profile import calculate_activity_summaries

router = APIRouter(tags=["athlete-profile"])


class AthleteProfileRequest(CalendarPeriodRequest):
    """Selected calendar period for the current athlete's persisted history."""


def get_athlete_profile_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> AthleteProfileRepository:
    return AthleteProfileRepository(session)


@router.post("/athlete-profile", response_model=AthleteProfile)
def build_athlete_profile(
    request: AthleteProfileRequest,
    repository: Annotated[
        AthleteProfileRepository,
        Depends(get_athlete_profile_repository),
    ],
) -> AthleteProfile:
    bounds = calendar_period_bounds(
        request.start_date, request.end_date, request.timezone
    )
    try:
        history = repository.load_current_history(
            start_at=bounds.start_at,
            end_at_exclusive=bounds.end_at_exclusive,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "athlete_profile_unavailable",
                "message": "The saved activity history is temporarily unavailable.",
            },
        ) from exc

    if history is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "strava_connection_required",
                "message": "Connect Strava before building an athlete profile.",
            },
        )

    return calculate_activity_summaries(
        history.activities,
        period_start=request.start_date,
        period_end=request.end_date,
        timezone=request.timezone,
    )
