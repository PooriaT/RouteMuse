from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.db.models import StravaConnection
from app.db.repositories.strava import StravaConnectionStatus
from app.integrations.strava.client import StravaOAuthClient
from app.integrations.strava.dependencies import (
    get_strava_connection_repository,
    get_strava_oauth_client,
)
from app.main import create_app

ACCESS_TOKEN = "never-serialize-access-token"
REFRESH_TOKEN = "never-serialize-refresh-token"
ROTATED_REFRESH_TOKEN = "never-serialize-rotated-refresh-token"


class FakeStravaConnectionRepository:
    def __init__(self) -> None:
        self.connection: StravaConnection | None = None
        self.commits = 0
        self.rollbacks = 0

    def get_current(self, *, for_update: bool = False) -> StravaConnection | None:
        return self.connection

    def get_status(self) -> StravaConnectionStatus | None:
        if self.connection is None:
            return None
        return StravaConnectionStatus(
            athlete_id=self.connection.strava_athlete_id,
            granted_scopes=self.connection.granted_scopes,
        )

    def upsert(
        self,
        *,
        athlete_id: int,
        access_token: str,
        refresh_token: str,
        access_token_expires_at: datetime,
        granted_scopes: list[str],
    ) -> StravaConnection:
        self.connection = StravaConnection(
            strava_athlete_id=athlete_id,
            access_token=access_token,
            refresh_token=refresh_token,
            access_token_expires_at=access_token_expires_at,
            granted_scopes=granted_scopes,
            connected_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        return self.connection

    def delete(self, connection: StravaConnection) -> None:
        assert connection is self.connection
        self.connection = None

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class StravaHTTPMock:
    def __init__(self) -> None:
        self.token_status = 200
        self.token_scope = "activity:read_all"
        self.revoke_status = 200
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        form = parse_qs(request.content.decode("utf-8"))
        if request.url.path == "/oauth/token":
            assert request.url.query == b""
            assert form["code"] == ["valid-authorization-code"]
            assert form["client_secret"] == ["test-client-secret"]
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"message": "provider"})
            return httpx.Response(
                200,
                json={
                    "access_token": ACCESS_TOKEN,
                    "refresh_token": REFRESH_TOKEN,
                    "expires_at": int(
                        (datetime.now(UTC) + timedelta(hours=6)).timestamp()
                    ),
                    "scope": self.token_scope,
                    "athlete": {"id": 9223372036854775000, "username": "ignored"},
                },
            )
        if request.url.path == "/oauth/revoke":
            assert request.url.query == b""
            assert form == {
                "token": [REFRESH_TOKEN],
                "token_type_hint": ["refresh_token"],
            }
            assert request.headers["Authorization"].startswith("Basic ")
            return httpx.Response(self.revoke_status)
        raise AssertionError(f"Unexpected Strava request path: {request.url.path}")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        database_url="postgresql+psycopg://unused/unused",
        strava_client_id="12345",
        strava_client_secret="test-client-secret",
        strava_redirect_uri="http://testserver/api/v1/strava/callback",
        strava_token_encryption_key=Fernet.generate_key().decode("ascii"),
        _env_file=None,
    )


@pytest.fixture
def repository() -> FakeStravaConnectionRepository:
    return FakeStravaConnectionRepository()


@pytest.fixture
def strava_http_mock() -> StravaHTTPMock:
    return StravaHTTPMock()


@pytest.fixture
def client(
    settings: Settings,
    repository: FakeStravaConnectionRepository,
    strava_http_mock: StravaHTTPMock,
) -> Iterator[TestClient]:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(strava_http_mock))
    oauth_client = StravaOAuthClient(settings, http_client=http_client)
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_strava_oauth_client] = lambda: oauth_client
    application.dependency_overrides[get_strava_connection_repository] = (
        lambda: repository
    )
    with TestClient(application) as test_client:
        yield test_client


def _authorization_state(client: TestClient) -> str:
    response = client.get("/api/v1/strava/connect", follow_redirects=False)
    assert response.status_code == 302
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def _successful_callback(client: TestClient) -> httpx.Response:
    state_value = _authorization_state(client)
    return client.get(
        "/api/v1/strava/callback",
        params={
            "code": "valid-authorization-code",
            "state": state_value,
            "scope": "activity:read_all",
        },
    )


def _assert_no_credentials(response: httpx.Response) -> None:
    serialized = response.text
    assert ACCESS_TOKEN not in serialized
    assert REFRESH_TOKEN not in serialized
    assert ROTATED_REFRESH_TOKEN not in serialized
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized
    assert "client_secret" not in serialized
    assert "valid-authorization-code" not in serialized


def test_connect_redirects_to_strava_with_minimum_scope_and_secure_state(
    client: TestClient,
) -> None:
    first = client.get("/api/v1/strava/connect", follow_redirects=False)
    second = client.get("/api/v1/strava/connect", follow_redirects=False)

    first_url = urlparse(first.headers["location"])
    first_query = parse_qs(first_url.query)
    second_state = parse_qs(urlparse(second.headers["location"]).query)["state"][0]

    assert first.status_code == 302
    assert (first_url.scheme, first_url.netloc, first_url.path) == (
        "https",
        "www.strava.com",
        "/oauth/authorize",
    )
    assert first_query == {
        "client_id": ["12345"],
        "redirect_uri": ["http://testserver/api/v1/strava/callback"],
        "response_type": ["code"],
        "approval_prompt": ["auto"],
        "scope": ["activity:read_all"],
        "state": [first_query["state"][0]],
    }
    assert len(first_query["state"][0]) >= 43
    assert first_query["state"][0] != second_state
    set_cookie = first.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "max-age=600" in set_cookie
    assert ACCESS_TOKEN not in set_cookie
    assert REFRESH_TOKEN not in set_cookie


def test_connect_state_cookie_is_secure_outside_local_environments(
    settings: Settings,
    repository: FakeStravaConnectionRepository,
) -> None:
    production_settings = settings.model_copy(update={"environment": "production"})
    application = create_app(production_settings)
    application.dependency_overrides[get_settings] = lambda: production_settings
    application.dependency_overrides[get_strava_connection_repository] = (
        lambda: repository
    )

    with TestClient(application) as production_client:
        response = production_client.get(
            "/api/v1/strava/connect", follow_redirects=False
        )

    assert "secure" in response.headers["set-cookie"].lower()


def test_missing_configuration_is_controlled_and_health_still_works() -> None:
    settings = Settings(environment="test", _env_file=None)
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings

    with TestClient(application) as test_client:
        connect_response = test_client.get(
            "/api/v1/strava/connect", follow_redirects=False
        )
        health_response = test_client.get("/health")

    assert connect_response.status_code == 503
    assert connect_response.json()["detail"]["code"] == (
        "strava_configuration_unavailable"
    )
    assert health_response.status_code == 200


def test_successful_callback_persists_connection_without_leaking_tokens(
    client: TestClient, repository: FakeStravaConnectionRepository
) -> None:
    response = _successful_callback(client)

    assert response.status_code == 200
    assert response.json() == {
        "connected": True,
        "athlete_id": "9223372036854775000",
        "granted_scopes": ["activity:read_all"],
    }
    assert repository.connection is not None
    assert repository.connection.access_token == ACCESS_TOKEN
    assert repository.connection.refresh_token == REFRESH_TOKEN
    assert repository.commits == 1
    assert "max-age=0" in response.headers["set-cookie"].lower()
    _assert_no_credentials(response)


@pytest.mark.parametrize(
    ("callback_params", "expected_code"),
    [
        ({"error": "access_denied"}, "strava_authorization_denied"),
        ({"scope": "activity:read_all"}, "strava_callback_malformed"),
        (
            {"code": "valid-authorization-code", "scope": "activity:read"},
            "strava_insufficient_scope",
        ),
    ],
)
def test_callback_errors_are_controlled_and_clear_state(
    client: TestClient,
    callback_params: dict[str, str],
    expected_code: str,
) -> None:
    state_value = _authorization_state(client)
    response = client.get(
        "/api/v1/strava/callback",
        params={"state": state_value, **callback_params},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == expected_code
    assert "max-age=0" in response.headers["set-cookie"].lower()
    _assert_no_credentials(response)


def test_callback_rejects_bad_state_and_clears_cookie(client: TestClient) -> None:
    _authorization_state(client)
    response = client.get(
        "/api/v1/strava/callback",
        params={
            "state": "attacker-state",
            "code": "valid-authorization-code",
            "scope": "activity:read_all",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "strava_oauth_state_invalid"
    assert "max-age=0" in response.headers["set-cookie"].lower()


def test_callback_rejects_missing_state(client: TestClient) -> None:
    response = client.get(
        "/api/v1/strava/callback",
        params={
            "code": "valid-authorization-code",
            "scope": "activity:read_all",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "strava_oauth_state_invalid"
    _assert_no_credentials(response)


def test_callback_rejects_unknown_provider_error_as_malformed(
    client: TestClient,
) -> None:
    state_value = _authorization_state(client)

    response = client.get(
        "/api/v1/strava/callback",
        params={"state": state_value, "error": "unexpected_provider_result"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "strava_callback_malformed"
    assert "max-age=0" in response.headers["set-cookie"].lower()


def test_callback_rejects_scope_missing_from_token_response(
    client: TestClient, strava_http_mock: StravaHTTPMock
) -> None:
    strava_http_mock.token_scope = "activity:read"

    response = _successful_callback(client)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "strava_insufficient_scope"
    assert [request.url.path for request in strava_http_mock.requests] == [
        "/oauth/token",
        "/oauth/revoke",
    ]
    _assert_no_credentials(response)


def test_callback_handles_failed_token_exchange(
    client: TestClient, strava_http_mock: StravaHTTPMock
) -> None:
    strava_http_mock.token_status = 503

    response = _successful_callback(client)

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "strava_token_exchange_failed"
    _assert_no_credentials(response)


def test_status_reports_connected_and_disconnected_without_tokens(
    client: TestClient,
) -> None:
    disconnected = client.get("/api/v1/strava/status")
    callback = _successful_callback(client)
    connected = client.get("/api/v1/strava/status")

    assert disconnected.json() == {
        "connected": False,
        "athlete_id": None,
        "granted_scopes": [],
    }
    assert connected.json() == callback.json()
    _assert_no_credentials(disconnected)
    _assert_no_credentials(connected)


def test_disconnect_revokes_refresh_token_then_removes_local_connection(
    client: TestClient,
    repository: FakeStravaConnectionRepository,
    strava_http_mock: StravaHTTPMock,
) -> None:
    _successful_callback(client)

    response = client.post("/api/v1/strava/disconnect")

    assert response.status_code == 200
    assert response.json() == {
        "connected": False,
        "athlete_id": None,
        "granted_scopes": [],
    }
    assert repository.connection is None
    assert strava_http_mock.requests[-1].url.path == "/oauth/revoke"
    _assert_no_credentials(response)


def test_disconnect_keeps_local_connection_when_remote_revocation_fails(
    client: TestClient,
    repository: FakeStravaConnectionRepository,
    strava_http_mock: StravaHTTPMock,
) -> None:
    _successful_callback(client)
    strava_http_mock.revoke_status = 503

    response = client.post("/api/v1/strava/disconnect")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "strava_token_revocation_failed"
    assert repository.connection is not None
    assert repository.rollbacks == 1
    _assert_no_credentials(response)


def test_disconnect_cleans_up_when_revocation_confirms_token_already_absent(
    client: TestClient,
    repository: FakeStravaConnectionRepository,
) -> None:
    # Strava's current revoke endpoint returns 200 even when the token is not found.
    _successful_callback(client)

    response = client.post("/api/v1/strava/disconnect")

    assert response.status_code == 200
    assert repository.connection is None
