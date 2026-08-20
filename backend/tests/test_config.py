from app.core.config import Settings


def test_configuration_loading(monkeypatch) -> None:
    monkeypatch.setenv("APP_NAME", "Test API")
    monkeypatch.setenv("CORS_ORIGINS", "http://one.test, http://two.test")
    settings = Settings(_env_file=None)
    assert settings.app_name == "Test API"
    assert settings.cors_origins == ["http://one.test", "http://two.test"]


def test_configuration_accepts_an_explicit_cors_origin_list() -> None:
    settings = Settings(cors_origins=["https://app.example.com"], _env_file=None)
    assert settings.cors_origins == ["https://app.example.com"]
