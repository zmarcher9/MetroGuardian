"""
Tests for the production startup guards in app.core.config.get_settings().

These bypass the @lru_cache wrapper (via __wrapped__) so each test builds a
fresh Settings instance from the environment instead of reusing whatever the
rest of the suite already cached.
"""
import pytest

from app.core.config import get_settings


def _fresh_settings():
    return get_settings.__wrapped__()


def test_local_env_boots_with_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "local")
    settings = _fresh_settings()
    assert settings.app_env == "local"


def test_production_rejects_default_jwt_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "changeme")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://app.example.com")
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        _fresh_settings()


def test_production_rejects_short_jwt_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "short")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://app.example.com")
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        _fresh_settings()


def test_production_rejects_wildcard_cors_with_credentials(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "a-properly-random-secret-key-1234567890")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")
    with pytest.raises(ValueError, match="CORS_ALLOW_ORIGINS"):
        _fresh_settings()


def test_production_allows_wildcard_cors_without_credentials(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "a-properly-random-secret-key-1234567890")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "false")
    settings = _fresh_settings()
    assert settings.cors_allow_origins == "*"


def test_production_allows_explicit_origins_with_credentials(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "a-properly-random-secret-key-1234567890")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")
    settings = _fresh_settings()
    assert settings.cors_allow_origins == "https://app.example.com"


def test_masked_database_url_hides_password():
    settings = _fresh_settings()
    masked = settings.get_database_url_masked()
    assert "@" in masked
    credentials_part = masked.split("@", 1)[0]
    # The password segment (after the last ':') must be exactly masked, not
    # merely "doesn't appear elsewhere" (a password that coincidentally
    # matches a substring of the host/dbname would false-positive that check).
    assert credentials_part.rsplit(":", 1)[-1] == "***"
