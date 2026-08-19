from fastapi import APIRouter

from app.api.routes.activity_types import router as activity_types_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(activity_types_router)
