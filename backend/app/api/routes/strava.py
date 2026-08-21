import hmac
import re
import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.db.repositories.strava import StravaConnectionRepository
from app.db.security import TokenProtectionError
from app.integrations.strava.client import REQUIRED_STRAVA_SCOPE, StravaOAuthClient
from app.integrations.strava.dependencies import (
    get_strava_connection_repository,
    get_strava_oauth_client,
)
from app.integrations.strava.errors import (
    StravaAuthenticationInvalid,
    StravaAuthorizationDenied,
    StravaCallbackMalformed,
    StravaConfigurationUnavailable,
    StravaInsufficientScope,
    StravaIntegrationError,
    StravaOAuthStateInvalid,
    StravaTokenExchangeFailed,
    StravaTokenRefreshFailed,
    StravaTokenRevocationFailed,
)

STRAVA_STATE_COOKIE = "routemuse_strava_oauth_state"
STRAVA_STATE_MAX_AGE_SECONDS = 600
STRAVA_CALLBACK_PATH = "/api/v1/strava/callback"

router = APIRouter(prefix="/strava", tags=["strava"])


class StravaConnectionStatusResponse(BaseModel):
    connected: bool
    athlete_id: str | None = None
    granted_scopes: list[str] = Field(default_factory=list)


def _secure_cookie(settings: Settings) -> bool:
    return settings.environment.lower() not in {"development", "local", "test"}


def _clear_state_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        STRAVA_STATE_COOKIE,
        path=STRAVA_CALLBACK_PATH,
        secure=_secure_cookie(settings),
        httponly=True,
        samesite="lax",
    )


def _parse_scopes(scope: str) -> set[str]:
    return {value for value in re.split(r"[\s,]+", scope.strip()) if value}


def _require_scope(scope: str | None) -> set[str]:
    if scope is None:
        raise StravaCallbackMalformed(
            "The Strava callback did not include granted scopes."
        )
    granted_scopes = _parse_scopes(scope)
    if REQUIRED_STRAVA_SCOPE not in granted_scopes:
        raise StravaInsufficientScope(
            "Private activity read access is required to connect Strava."
        )
    return granted_scopes


@router.get("/connect")
async def connect_strava(
    oauth_client: Annotated[StravaOAuthClient, Depends(get_strava_oauth_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    state_value = secrets.token_urlsafe(32)
    authorization_url = oauth_client.authorization_url(state_value)
    response = RedirectResponse(
        authorization_url, status_code=status.HTTP_302_FOUND
    )
    response.set_cookie(
        STRAVA_STATE_COOKIE,
        state_value,
        max_age=STRAVA_STATE_MAX_AGE_SECONDS,
        path=STRAVA_CALLBACK_PATH,
        secure=_secure_cookie(settings),
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/callback", response_model=StravaConnectionStatusResponse)
async def strava_callback(
    response: Response,
    oauth_client: Annotated[StravaOAuthClient, Depends(get_strava_oauth_client)],
    repository: Annotated[
        StravaConnectionRepository, Depends(get_strava_connection_repository)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    code: Annotated[str | None, Query()] = None,
    state_value: Annotated[str | None, Query(alias="state")] = None,
    scope: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    cookie_state: Annotated[str | None, Cookie(alias=STRAVA_STATE_COOKIE)] = None,
) -> StravaConnectionStatusResponse:
    if not state_value or not cookie_state or not hmac.compare_digest(
        state_value, cookie_state
    ):
        raise StravaOAuthStateInvalid(
            "The Strava authorization state is missing, expired, or invalid."
        )
    if error == "access_denied":
        raise StravaAuthorizationDenied("Strava authorization was denied.")
    if error is not None:
        raise StravaCallbackMalformed("Strava returned an unsupported OAuth error.")
    if not code:
        raise StravaCallbackMalformed(
            "The Strava callback did not include an authorization code."
        )

    _require_scope(scope)
    token_result = await oauth_client.exchange_code(code)
    try:
        granted_scopes = _require_scope(token_result.scope)
    except StravaInsufficientScope:
        # Do not retain an unusable provider grant after the user declines the
        # minimum scope in Strava's consent screen.
        await oauth_client.revoke_token(
            token_result.refresh_token.get_secret_value()
        )
        raise
    try:
        connection = repository.upsert(
            athlete_id=token_result.athlete.id,
            access_token=token_result.access_token.get_secret_value(),
            refresh_token=token_result.refresh_token.get_secret_value(),
            access_token_expires_at=datetime.fromtimestamp(
                token_result.expires_at, tz=UTC
            ),
            granted_scopes=sorted(granted_scopes),
        )
        repository.commit()
    except TokenProtectionError as exc:
        repository.rollback()
        raise StravaConfigurationUnavailable(
            "Protected Strava token storage is unavailable."
        ) from exc

    _clear_state_cookie(response, settings)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return StravaConnectionStatusResponse(
        connected=True,
        athlete_id=str(connection.strava_athlete_id),
        granted_scopes=sorted(granted_scopes),
    )


@router.get("/status", response_model=StravaConnectionStatusResponse)
def strava_status(
    response: Response,
    repository: Annotated[
        StravaConnectionRepository, Depends(get_strava_connection_repository)
    ],
) -> StravaConnectionStatusResponse:
    response.headers["Cache-Control"] = "no-store"
    connection_status = repository.get_status()
    if connection_status is None:
        return StravaConnectionStatusResponse(connected=False)
    return StravaConnectionStatusResponse(
        connected=True,
        athlete_id=str(connection_status.athlete_id),
        granted_scopes=sorted(connection_status.granted_scopes),
    )


@router.post("/disconnect", response_model=StravaConnectionStatusResponse)
async def disconnect_strava(
    response: Response,
    oauth_client: Annotated[StravaOAuthClient, Depends(get_strava_oauth_client)],
    repository: Annotated[
        StravaConnectionRepository, Depends(get_strava_connection_repository)
    ],
) -> StravaConnectionStatusResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        connection = repository.get_current(for_update=True)
    except TokenProtectionError as exc:
        repository.rollback()
        raise StravaConfigurationUnavailable(
            "Protected Strava token material is unavailable."
        ) from exc
    if connection is None:
        repository.rollback()
        return StravaConnectionStatusResponse(connected=False)

    try:
        await oauth_client.revoke_token(connection.refresh_token)
    except StravaIntegrationError:
        repository.rollback()
        raise
    repository.delete(connection)
    repository.commit()
    return StravaConnectionStatusResponse(connected=False)


_ERROR_RESPONSES: tuple[
    tuple[type[StravaIntegrationError], int, str, str], ...
] = (
    (
        StravaConfigurationUnavailable,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "strava_configuration_unavailable",
        "Strava integration configuration is unavailable.",
    ),
    (
        StravaAuthorizationDenied,
        status.HTTP_400_BAD_REQUEST,
        "strava_authorization_denied",
        "Strava authorization was denied.",
    ),
    (
        StravaOAuthStateInvalid,
        status.HTTP_400_BAD_REQUEST,
        "strava_oauth_state_invalid",
        "The Strava authorization state is missing, expired, or invalid.",
    ),
    (
        StravaCallbackMalformed,
        status.HTTP_400_BAD_REQUEST,
        "strava_callback_malformed",
        "The Strava OAuth callback is malformed.",
    ),
    (
        StravaInsufficientScope,
        status.HTTP_400_BAD_REQUEST,
        "strava_insufficient_scope",
        "Private activity read access is required.",
    ),
    (
        StravaTokenExchangeFailed,
        status.HTTP_502_BAD_GATEWAY,
        "strava_token_exchange_failed",
        "Strava did not complete the token exchange.",
    ),
    (
        StravaTokenRefreshFailed,
        status.HTTP_502_BAD_GATEWAY,
        "strava_token_refresh_failed",
        "Strava did not complete the token refresh.",
    ),
    (
        StravaTokenRevocationFailed,
        status.HTTP_502_BAD_GATEWAY,
        "strava_token_revocation_failed",
        "Strava did not confirm revocation; retry is safe.",
    ),
    (
        StravaAuthenticationInvalid,
        status.HTTP_401_UNAUTHORIZED,
        "strava_authentication_invalid",
        "The Strava connection is no longer authenticated.",
    ),
)


async def strava_exception_handler(
    request: Request, exc: StravaIntegrationError
) -> JSONResponse:
    for exception_type, status_code, code, message in _ERROR_RESPONSES:
        if isinstance(exc, exception_type):
            response = JSONResponse(
                status_code=status_code,
                content={"detail": {"code": code, "message": message}},
                headers={
                    "Cache-Control": "no-store",
                    "Referrer-Policy": "no-referrer",
                },
            )
            if request.url.path == STRAVA_CALLBACK_PATH:
                _clear_state_cookie(response, request.app.state.settings)
            return response
    response = JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "detail": {
                "code": "strava_integration_error",
                "message": "The Strava integration could not complete the request.",
            }
        },
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
    if request.url.path == STRAVA_CALLBACK_PATH:
        _clear_state_cookie(response, request.app.state.settings)
    return response
