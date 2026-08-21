import pytest
from cryptography.fernet import Fernet

from app.db.models import StravaConnection
from app.db.security import (
    EncryptedToken,
    TokenDecryptionError,
    TokenEncryptionConfigurationError,
    TokenProtector,
)


@pytest.fixture
def token_protector() -> TokenProtector:
    return TokenProtector(Fernet.generate_key().decode("ascii"))


def test_encrypt_then_decrypt_returns_original_token(
    token_protector: TokenProtector,
) -> None:
    token = "provider-token-value"

    ciphertext = token_protector.encrypt(token)

    assert ciphertext != token.encode("utf-8")
    assert token_protector.decrypt(ciphertext) == token


def test_invalid_key_fails_without_exposing_key() -> None:
    invalid_key = "definitely-not-a-fernet-key"

    with pytest.raises(TokenEncryptionConfigurationError) as error:
        TokenProtector(invalid_key)

    assert invalid_key not in str(error.value)


def test_invalid_ciphertext_fails_without_exposing_ciphertext(
    token_protector: TokenProtector,
) -> None:
    invalid_ciphertext = b"not-valid-ciphertext"

    with pytest.raises(TokenDecryptionError) as error:
        token_protector.decrypt(invalid_ciphertext)

    assert invalid_ciphertext.decode() not in str(error.value)


def test_encrypted_sqlalchemy_type_binds_only_ciphertext(
    monkeypatch: pytest.MonkeyPatch, token_protector: TokenProtector
) -> None:
    monkeypatch.setattr(
        "app.db.security.get_strava_token_protector", lambda: token_protector
    )
    token_type = EncryptedToken()
    plaintext = "database-must-not-see-this-token"

    bound_value = token_type.process_bind_param(plaintext, dialect=None)  # type: ignore[arg-type]

    assert bound_value != plaintext.encode()
    assert plaintext.encode() not in bound_value
    assert (
        token_type.process_result_value(  # type: ignore[arg-type]
            bound_value, dialect=None
        )
        == plaintext
    )


def test_connection_schema_only_has_ciphertext_token_columns() -> None:
    table = StravaConnection.__table__

    assert "access_token" not in table.c
    assert "refresh_token" not in table.c
    assert isinstance(table.c.access_token_ciphertext.type, EncryptedToken)
    assert isinstance(table.c.refresh_token_ciphertext.type, EncryptedToken)
