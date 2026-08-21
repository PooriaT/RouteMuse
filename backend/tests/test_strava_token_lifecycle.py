import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr
from sqlalchemy.exc import StatementError

from app.db.models import StravaConnection
from app.db.repositories.strava import StravaConnectionRepository
from app.db.security import TokenEncryptionConfigurationError
from app.integrations.strava.dtos import StravaTokenRefreshDTO
from app.integrations.strava.errors import StravaTokenRefreshFailed
from app.integrations.strava.tokens import StravaTokenService


class FakeLifecycleRepository:
    def __init__(self, connection: StravaConnection | None) -> None:
        self.connection = connection
        self.for_update = False
        self.commits = 0
        self.rollbacks = 0

    def get_current(self, *, for_update: bool = False) -> StravaConnection | None:
        self.for_update = for_update
        return self.connection

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakeRefreshClient:
    def __init__(
        self,
        result: StravaTokenRefreshDTO | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.refresh_calls: list[str] = []

    async def refresh_token(self, refresh_token: str) -> StravaTokenRefreshDTO:
        self.refresh_calls.append(refresh_token)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _connection(expires_at: datetime) -> StravaConnection:
    return StravaConnection(
        strava_athlete_id=123,
        access_token="current-access",
        refresh_token="current-refresh",
        access_token_expires_at=expires_at,
        granted_scopes=["activity:read_all"],
        connected_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_still_valid_access_token_is_reused() -> None:
    connection = _connection(datetime.now(UTC) + timedelta(hours=2))
    repository = FakeLifecycleRepository(connection)
    oauth_client = FakeRefreshClient()
    service = StravaTokenService(repository, oauth_client)  # type: ignore[arg-type]

    token = asyncio.run(service.usable_access_token())

    assert token == "current-access"
    assert oauth_client.refresh_calls == []
    assert repository.for_update is True
    assert repository.commits == 1


@pytest.mark.parametrize("expiry_delta", [timedelta(minutes=59), timedelta(seconds=-1)])
def test_near_expiry_or_expired_token_is_refreshed_and_rotation_is_persisted(
    expiry_delta: timedelta,
) -> None:
    connection = _connection(datetime.now(UTC) + expiry_delta)
    refreshed_expiry = int((datetime.now(UTC) + timedelta(hours=6)).timestamp())
    repository = FakeLifecycleRepository(connection)
    oauth_client = FakeRefreshClient(
        StravaTokenRefreshDTO(
            access_token=SecretStr("new-access"),
            refresh_token=SecretStr("rotated-refresh"),
            expires_at=refreshed_expiry,
        )
    )
    service = StravaTokenService(repository, oauth_client)  # type: ignore[arg-type]

    token = asyncio.run(service.usable_access_token())

    assert token == "new-access"
    assert connection.access_token == "new-access"
    assert connection.refresh_token == "rotated-refresh"
    assert connection.access_token_expires_at == datetime.fromtimestamp(
        refreshed_expiry, tz=UTC
    )
    assert oauth_client.refresh_calls == ["current-refresh"]
    assert repository.commits == 1


def test_provider_unauthorized_can_force_refresh_through_lifecycle_service() -> None:
    connection = _connection(datetime.now(UTC) + timedelta(hours=6))
    refreshed_expiry = int((datetime.now(UTC) + timedelta(hours=8)).timestamp())
    repository = FakeLifecycleRepository(connection)
    oauth_client = FakeRefreshClient(
        StravaTokenRefreshDTO(
            access_token=SecretStr("forced-access"),
            refresh_token=SecretStr("forced-rotated-refresh"),
            expires_at=refreshed_expiry,
        )
    )
    service = StravaTokenService(repository, oauth_client)  # type: ignore[arg-type]

    token = asyncio.run(service.refresh_access_token())

    assert token == "forced-access"
    assert oauth_client.refresh_calls == ["current-refresh"]
    assert connection.refresh_token == "forced-rotated-refresh"
    assert repository.commits == 1


def test_failed_refresh_rolls_back_without_changing_tokens() -> None:
    connection = _connection(datetime.now(UTC) - timedelta(seconds=1))
    repository = FakeLifecycleRepository(connection)
    oauth_client = FakeRefreshClient(
        error=StravaTokenRefreshFailed("safe provider failure")
    )
    service = StravaTokenService(repository, oauth_client)  # type: ignore[arg-type]

    with pytest.raises(StravaTokenRefreshFailed):
        asyncio.run(service.usable_access_token())

    assert connection.access_token == "current-access"
    assert connection.refresh_token == "current-refresh"
    assert repository.commits == 0
    assert repository.rollbacks == 1


def test_repository_uses_row_lock_for_refresh_serialization() -> None:
    session = MagicMock()
    repository = StravaConnectionRepository(session)

    repository.get_current(for_update=True)

    statement = session.scalar.call_args.args[0]
    assert "FOR UPDATE" in str(statement)


def test_repository_preserves_controlled_token_protection_error() -> None:
    session = MagicMock()
    session.commit.side_effect = StatementError(
        "statement failed",
        None,
        None,
        TokenEncryptionConfigurationError("safe configuration error"),
    )
    repository = StravaConnectionRepository(session)

    with pytest.raises(TokenEncryptionConfigurationError) as error:
        repository.commit()

    assert str(error.value) == "safe configuration error"


def test_repository_replaces_different_athlete_in_singleton_slot() -> None:
    existing = _connection(datetime.now(UTC) + timedelta(hours=2))
    existing.id = 10
    session = MagicMock()
    session.scalar.return_value = existing
    repository = StravaConnectionRepository(session)

    replacement = repository.upsert(
        athlete_id=456,
        access_token="replacement-access",
        refresh_token="replacement-refresh",
        access_token_expires_at=datetime.now(UTC) + timedelta(hours=6),
        granted_scopes=["activity:read_all"],
    )

    session.delete.assert_called_once_with(existing)
    session.flush.assert_called_once_with()
    session.add.assert_called_once_with(replacement)
    assert replacement is not existing
    assert replacement.singleton_slot is True
    assert replacement.strava_athlete_id == 456
