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
    student_workspace_dir: Path = Path(".")
    daemon_socket_path: Path = Path("/run/unicode/daemon.sock")
    session_ttl_seconds: int = 14400
    admin_password: str = "change-me-in-prod"
    sandbox_image: str = "unicode-sandbox"
    sandbox_timeout_seconds: int = 5
    sandbox_memory_mb: int = 256
    sandbox_cpus: float = 0.5
    sandbox_pids_limit: int = 64


def get_settings() -> Settings:
    """Return a new configuration instance loaded from current environment."""
    return Settings()
