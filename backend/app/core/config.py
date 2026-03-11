import logging
from functools import lru_cache
from pathlib import Path
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

