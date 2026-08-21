from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.repositories.strava import StravaConnectionRepository
from app.db.session import get_db_session
from app.integrations.strava.client import StravaOAuthClient
from app.integrations.strava.tokens import StravaTokenService


def get_strava_connection_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> StravaConnectionRepository:
    return StravaConnectionRepository(session)


def get_strava_oauth_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> StravaOAuthClient:
    return StravaOAuthClient(settings)


def get_strava_token_service(
    repository: Annotated[
        StravaConnectionRepository, Depends(get_strava_connection_repository)
    ],
    oauth_client: Annotated[StravaOAuthClient, Depends(get_strava_oauth_client)],
) -> StravaTokenService:
    return StravaTokenService(repository, oauth_client)
