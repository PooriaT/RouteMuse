from fastapi import APIRouter

from app.api.routes.activity_types import router as activity_types_router
from app.api.routes.athlete_profile import router as athlete_profile_router
from app.api.routes.planning_areas import router as planning_areas_router
from app.api.routes.strava import router as strava_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(activity_types_router)
api_router.include_router(athlete_profile_router)
api_router.include_router(strava_router)
api_router.include_router(planning_areas_router)
