from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration for UniCode loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="UNICODE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://unicode_daemon:unicode_daemon@localhost:5432/unicode"
    migrations_database_url: str = (
        "postgresql://unicode_owner:unicode_owner@localhost:5432/unicode"
    )
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    questions_dir: Path = Path("questions")
    workspaces_dir: Path = Path("/srv/unicode/workspaces")
    daemon_socket_path: Path = Path("/run/unicode/daemon.sock")
    admin_password: str = "change-me-in-prod"


def get_settings() -> Settings:
    """Return a new configuration instance loaded from current environment."""
    return Settings()
