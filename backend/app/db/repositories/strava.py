from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from app.db.models import StravaConnection
from app.db.security import TokenProtectionError


@dataclass(frozen=True)
class StravaConnectionStatus:
    athlete_id: int
    granted_scopes: list[str]


class StravaConnectionRepository:
    """Persistence operations used by Strava OAuth and token lifecycle services."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_current(self, *, for_update: bool = False) -> StravaConnection | None:
        statement: Select[tuple[StravaConnection]] = (
            select(StravaConnection)
            .order_by(StravaConnection.updated_at.desc(), StravaConnection.id.desc())
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        try:
            return self._session.scalar(statement)
        except StatementError as exc:
            self._raise_token_protection_error(exc)

    def get_status(self) -> StravaConnectionStatus | None:
        row = self._session.execute(
            select(
                StravaConnection.strava_athlete_id,
                StravaConnection.granted_scopes,
            )
            .order_by(StravaConnection.updated_at.desc(), StravaConnection.id.desc())
            .limit(1)
        ).one_or_none()
        if row is None:
            return None
        return StravaConnectionStatus(athlete_id=row[0], granted_scopes=row[1])

    def upsert(
        self,
        *,
        athlete_id: int,
        access_token: str,
        refresh_token: str,
        access_token_expires_at: datetime,
        granted_scopes: list[str],
    ) -> StravaConnection:
        connection = self._session.scalar(
            select(StravaConnection).where(
                StravaConnection.strava_athlete_id == athlete_id
            )
        )
        now = datetime.now(UTC)
        if connection is None:
            connection = StravaConnection(
                strava_athlete_id=athlete_id,
                access_token=access_token,
                refresh_token=refresh_token,
                access_token_expires_at=access_token_expires_at,
                granted_scopes=granted_scopes,
                connected_at=now,
                updated_at=now,
            )
            self._session.add(connection)
        else:
            connection.access_token = access_token
            connection.refresh_token = refresh_token
            connection.access_token_expires_at = access_token_expires_at
            connection.granted_scopes = granted_scopes
            connection.connected_at = now
            connection.updated_at = now
        return connection

    def delete(self, connection: StravaConnection) -> None:
        self._session.delete(connection)

    def commit(self) -> None:
        try:
            self._session.commit()
        except StatementError as exc:
            self._raise_token_protection_error(exc)

    def rollback(self) -> None:
        self._session.rollback()

    @staticmethod
    def _raise_token_protection_error(error: StatementError) -> None:
        if isinstance(error.orig, TokenProtectionError):
            raise error.orig from error
        raise error
