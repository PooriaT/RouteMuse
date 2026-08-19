from fastapi import APIRouter
from pydantic import BaseModel

from app.domain.activities import ActivityKind

router = APIRouter()


class ActivityTypeResponse(BaseModel):
    value: ActivityKind
    label: str


@router.get("/activity-types", response_model=list[ActivityTypeResponse])
def activity_types() -> list[ActivityTypeResponse]:
    return [
        ActivityTypeResponse(value=kind, label=kind.value.replace("_", " ").title())
        for kind in ActivityKind
    ]
