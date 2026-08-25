from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.api.routes.strava import (
    STRAVA_CALLBACK_PATH,
    strava_exception_handler,
)
from app.core.config import Settings, get_settings
from app.core.http import RedactOAuthCallbackQueryMiddleware
from app.core.logging import configure_logging
from app.integrations.geospatial.overpass import OverpassDiscoveryProvider
from app.integrations.strava.errors import StravaIntegrationError


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API without initializing databases or external providers."""
    resolved_settings = settings or get_settings()
    application = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)
    application.state.settings = resolved_settings
    application.state.overpass_discovery_provider = OverpassDiscoveryProvider(
        resolved_settings
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(
        RedactOAuthCallbackQueryMiddleware,
        callback_path=STRAVA_CALLBACK_PATH,
    )
    application.add_exception_handler(
        StravaIntegrationError, strava_exception_handler  # type: ignore[arg-type]
    )
    application.include_router(health_router)
    application.include_router(api_router)
    return application


app = create_app()
