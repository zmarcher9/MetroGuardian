import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _get_env_file_path() -> str:
    """
    Resolve .env file path relative to backend/ directory.
    This ensures the .env file is found regardless of where Python is run from.
    
    Returns:
        Absolute path to .env file as string
    """
    # Get the backend root directory (3 levels up from this file: app/core/config.py -> app/core -> app -> backend)
    backend_root = Path(__file__).parent.parent.parent
    env_file = (backend_root / ".env").resolve()
    return str(env_file)


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and .env file.
    
    Environment variables are automatically mapped:
    - DATABASE_HOST -> database_host
    - DATABASE_PORT -> database_port
    - etc.
    """
    
    # App settings
    app_env: str = Field(default="local", description="Application environment")
    app_name: str = Field(default="metroguardian-backend", description="Application name")

    # Database settings - Supabase compatible
    # Option 1: Use DATABASE_URL (Supabase provides this)
    database_url_raw: str | None = Field(
        default=None,
        alias="database_url",  # Allow DATABASE_URL env var to map to database_url_raw field
        description="Full database connection URL (Supabase format: postgresql://user:pass@host:port/dbname)"
    )
    
    # Option 2: Use individual components (fallback if DATABASE_URL not provided)
    database_host: str | None = Field(default=None, description="Database host address")
    database_port: int = Field(default=5432, description="Database port")
    database_user: str | None = Field(default=None, description="Database username")
    database_password: str | None = Field(default=None, description="Database password")
    database_name: str | None = Field(default=None, description="Database name")

    # JWT settings (optional, defaults provided)
    jwt_secret_key: str = Field(default="changeme", description="JWT secret key for token signing")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_access_token_expire_minutes: int = Field(
        default=15,
        description="Access token expiration time in minutes",
    )
    jwt_secret_key_min_length: int = Field(default=32, description="Min length for JWT secret in production")

    # Cookie-based auth settings
    access_token_cookie_name: str = Field(default="mg_at", description="Cookie name for the access token JWT")
    refresh_token_cookie_name: str = Field(default="mg_rt", description="Cookie name for the opaque refresh token")
    csrf_cookie_name: str = Field(default="mg_csrf", description="Cookie name for the CSRF double-submit token")
    csrf_header_name: str = Field(default="X-CSRF-Token", description="Header name clients must echo the CSRF cookie in")
    refresh_token_expire_days: int = Field(default=30, description="Refresh token expiration time in days")
    cookie_secure: bool = Field(default=True, description="Set the Secure attribute on auth cookies")
    cookie_samesite: Literal["lax", "strict", "none"] = Field(
        default="lax", description="SameSite attribute for auth cookies"
    )

    # Ingestion settings (Step 4)
    ingestion_enabled: bool = Field(default=True, description="Enable background ingestion loops on startup")
    ingestion_interval_seconds: int = Field(
        default=30,
        description="Seconds between ingestion runs (0 disables scheduling; manual trigger still works)",
    )
    traffic_simulated: bool = Field(default=True, description="Use simulated traffic data instead of a real API")
    construction_feed_path: str | None = Field(
        default=None,
        description="Optional path to a construction feed file (JSON). If unset, uses built-in sample feed.",
    )

    # Hardening (Step 7)
    cors_allow_origins: str = Field(
        default="*",
        description="Comma-separated origins for CORS, or * for all (dev only)",
    )
    cors_allow_credentials: bool = Field(default=True, description="CORS allow credentials")
    cors_allow_methods: str = Field(default="*", description="CORS allow methods (comma-separated) or *")
    cors_allow_headers: str = Field(default="*", description="CORS allow headers (comma-separated) or *")

    rate_limit_requests: int = Field(default=120, description="Max requests per window per IP")
    rate_limit_window_seconds: int = Field(default=60, description="Rate limit window size in seconds")

    # Stricter, auth-specific rate limits on top of the general one above -
    # 120 req/min is fine for general API use but far too permissive to slow
    # down credential-stuffing/brute-force login or mass fake-account signup.
    rate_limit_login_attempts: int = Field(default=5, description="Max login attempts per window per IP+email")
    rate_limit_login_window_seconds: int = Field(default=900, description="Login rate limit window (default 15 min)")
    rate_limit_signup_attempts: int = Field(default=5, description="Max signups per window per IP")
    rate_limit_signup_window_seconds: int = Field(default=3600, description="Signup rate limit window (default 1 hour)")

    # Background maintenance (refresh-token + ingestion-data cleanup share one loop/interval)
    maintenance_cleanup_interval_hours: int = Field(
        default=24, description="How often the background cleanup job runs (0 disables it)"
    )
    refresh_token_cleanup_grace_days: int = Field(
        default=7,
        description="Delete refresh_token rows this many days past expiry/revocation "
        "(kept briefly for incident forensics, not indefinitely)",
    )
    # TrafficEvent/ConstructionEvent are raw ingestion inputs with no read path
    # that ever looks back further than a few minutes (the anomaly-detection
    # window) or a page of "most recent N" results - short retention is safe.
    traffic_event_retention_days: int = Field(default=3, description="Delete TrafficEvent rows older than this")
    construction_event_retention_days: int = Field(
        default=3, description="Delete ConstructionEvent rows older than this"
    )
    # PipelineAlert is user-facing "alert history" (v1.2 roadmap) - keep much longer.
    pipeline_alert_retention_days: int = Field(default=90, description="Delete PipelineAlert rows older than this")

    # Routing (OSRM)
    osrm_base_url: str = Field(
        default="https://router.project-osrm.org",
        description="Base URL for an OSRM routing server (public demo or self-hosted)",
    )
    route_impact_radius_meters: float = Field(
        default=250.0,
        description="Max distance from a route line for an alert to count as impacting that route",
    )
    route_impact_lookback_minutes: int = Field(
        default=45,
        description="How far back to look for pipeline alerts when computing route impact",
    )

    model_config = SettingsConfigDict(
        env_file=str(_get_env_file_path()),
        env_file_encoding="utf-8",
        case_sensitive=False,  # Allow both UPPER_CASE and lower_case env vars
        extra="ignore",  # Ignore extra env vars not defined in model
        populate_by_name=True,  # Allow both field name and alias to work
    )

    @property
    def database_url(self) -> str:
        """
        Get async SQLAlchemy database URL for PostgreSQL.
        
        Supports Supabase connection strings:
        - If DATABASE_URL is provided, converts it to asyncpg format
        - Otherwise, builds from individual components
        
        Returns:
            PostgreSQL connection string using asyncpg driver
        """
        # If full DATABASE_URL is provided (Supabase style)
        if self.database_url_raw:
            raw_url = self.database_url_raw
            # Convert postgresql:// to postgresql+asyncpg://
            if raw_url.startswith("postgresql://"):
                return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            # Already in correct format
            if "postgresql+asyncpg://" in raw_url:
                return raw_url
            # If it's missing the scheme, add it
            if not raw_url.startswith(("postgresql://", "postgresql+asyncpg://")):
                return f"postgresql+asyncpg://{raw_url}"
            return raw_url
        
        # Fallback: Build from individual components
        if not all([self.database_host, self.database_user, self.database_password, self.database_name]):
            raise ValueError(
                "Either DATABASE_URL must be provided, or all of: "
                "DATABASE_HOST, DATABASE_USER, DATABASE_PASSWORD, DATABASE_NAME"
            )
        
        return (
            f"postgresql+asyncpg://{self.database_user}:"
            f"{self.database_password}@{self.database_host}:"
            f"{self.database_port}/{self.database_name}"
        )

    def get_database_url_masked(self) -> str:
        """
        Get database URL with password masked for logging/debugging.
        
        Returns:
            Database URL with password replaced with '***'
        """
        url = self.database_url
        # Mask password in connection string
        if "@" in url:
            # Extract parts before and after @
            parts = url.split("@", 1)
            if ":" in parts[0]:
                # Mask password: postgresql+asyncpg://user:pass@host -> postgresql+asyncpg://user:***@host
                scheme_user = parts[0].rsplit(":", 1)[0]  # Everything before the last :
                return f"{scheme_user}:***@{parts[1]}"
        return url.replace("postgresql+asyncpg://", "postgresql+asyncpg://***@", 1) if "postgresql+asyncpg://" in url else url


@lru_cache
def get_settings() -> Settings:
    """
    Get application settings singleton instance.
    
    Uses @lru_cache to ensure only one Settings instance is created,
    which is then reused across the application.
    
    Returns:
        Settings: Cached Settings instance
    """
    try:
        settings = Settings()
        # In production, refuse to run with default or weak JWT secret
        if settings.app_env == "production":
            if settings.jwt_secret_key == "changeme" or len(settings.jwt_secret_key) < settings.jwt_secret_key_min_length:
                raise ValueError(
                    f"JWT_SECRET_KEY must be set and at least {settings.jwt_secret_key_min_length} characters in production. "
                    "Set JWT_SECRET_KEY in .env or environment."
                )
            # Wildcard CORS origin combined with allow_credentials is both insecure and
            # rejected by browsers for credentialed requests - require explicit origins.
            if settings.cors_allow_origins.strip() == "*" and settings.cors_allow_credentials:
                raise ValueError(
                    "CORS_ALLOW_ORIGINS must not be '*' when CORS_ALLOW_CREDENTIALS is true in production. "
                    "Set CORS_ALLOW_ORIGINS to a comma-separated list of explicit origins."
                )
            # Auth cookies must never be sent over plaintext HTTP in production.
            if not settings.cookie_secure:
                raise ValueError(
                    "COOKIE_SECURE must be true in production. Auth cookies must not be sent over plain HTTP."
                )
        # Determine which database config method was used
        db_info = "DATABASE_URL" if settings.database_url_raw else "individual components"
        logger.info(
            f"Configuration loaded successfully | "
            f"env={settings.app_env} | "
            f"db_config={db_info} | "
            f"db_url={settings.get_database_url_masked()}"
        )
        return settings
    except Exception as e:
        logger.error(
            f"Failed to load configuration: {e} | "
            f"Make sure .env file exists at {_get_env_file_path()}"
        )
        raise

