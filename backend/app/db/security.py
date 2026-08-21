from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import LargeBinary, TypeDecorator

from app.core.config import get_settings


class TokenProtectionError(RuntimeError):
    """Base error for controlled failures while protecting OAuth tokens."""


class TokenEncryptionConfigurationError(TokenProtectionError):
    """Raised when token encryption is not configured with a valid Fernet key."""


class TokenDecryptionError(TokenProtectionError):
    """Raised when protected token material cannot be safely decrypted."""


class TokenProtector:
    """Encrypt and decrypt OAuth tokens with authenticated Fernet encryption."""

    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            raise TokenEncryptionConfigurationError(
                "STRAVA_TOKEN_ENCRYPTION_KEY must be a valid Fernet key."
            ) from exc

    def encrypt(self, token: str) -> bytes:
        if not isinstance(token, str) or not token:
            raise TokenProtectionError("A non-empty token is required.")
        return self._fernet.encrypt(token.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode("utf-8")
        except (InvalidToken, TypeError, UnicodeDecodeError) as exc:
            raise TokenDecryptionError(
                "Unable to decrypt protected Strava token material."
            ) from exc


@lru_cache(maxsize=4)
def _protector_for_key(key: str) -> TokenProtector:
    return TokenProtector(key)


def get_strava_token_protector() -> TokenProtector:
    configured_key = get_settings().strava_token_encryption_key
    if configured_key is None or not configured_key.get_secret_value():
        raise TokenEncryptionConfigurationError(
            "STRAVA_TOKEN_ENCRYPTION_KEY is required to store or read Strava tokens."
        )
    return _protector_for_key(configured_key.get_secret_value())


class EncryptedToken(TypeDecorator[str]):
    """SQLAlchemy type that only sends Fernet ciphertext to the database."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> bytes | None:
        if value is None:
            return None
        return get_strava_token_protector().encrypt(value)

    def process_result_value(self, value: bytes | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return get_strava_token_protector().decrypt(value)
