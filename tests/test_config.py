from pathlib import Path

import pytest

from unicode.config import Settings, get_settings


def test_settings_default_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "UNICODE_DATABASE_URL",
        "UNICODE_MIGRATIONS_DATABASE_URL",
        "UNICODE_DB_POOL_MIN_SIZE",
        "UNICODE_DB_POOL_MAX_SIZE",
        "UNICODE_QUESTIONS_DIR",
        "UNICODE_WORKSPACES_DIR",
        "UNICODE_DAEMON_SOCKET_PATH",
        "UNICODE_ADMIN_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=None)

    assert (
        settings.database_url
        == "postgresql://unicode_daemon:unicode_daemon@localhost:5432/unicode"
    )
    assert (
        settings.migrations_database_url
        == "postgresql://unicode_owner:unicode_owner@localhost:5432/unicode"
    )
    assert settings.db_pool_min_size == 1
    assert settings.db_pool_max_size == 10
    assert settings.questions_dir == Path("questions")
    assert settings.workspaces_dir == Path("/srv/unicode/workspaces")
    assert settings.daemon_socket_path == Path("/run/unicode/daemon.sock")
    assert settings.admin_password == "change-me-in-prod"


def test_settings_override_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNICODE_DATABASE_URL", "postgresql://user:pass@db:5432/test_db")
    monkeypatch.setenv("UNICODE_QUESTIONS_DIR", "/opt/unicode/questions")
    monkeypatch.setenv("UNICODE_ADMIN_PASSWORD", "secret-123")

    settings = get_settings()

    assert settings.database_url == "postgresql://user:pass@db:5432/test_db"
    assert settings.questions_dir == Path("/opt/unicode/questions")
    assert settings.admin_password == "secret-123"


def test_pool_sizes_override_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNICODE_DB_POOL_MIN_SIZE", "2")
    monkeypatch.setenv("UNICODE_DB_POOL_MAX_SIZE", "20")

    settings = Settings(_env_file=None)

    assert settings.db_pool_min_size == 2
    assert settings.db_pool_max_size == 20


def test_sandbox_settings_defaults_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    assert s.sandbox_image == "unicode-sandbox"
    assert s.sandbox_timeout_seconds == 5
    assert s.sandbox_memory_mb == 256
    assert s.sandbox_cpus == 0.5
    assert s.sandbox_pids_limit == 64

    monkeypatch.setenv("UNICODE_SANDBOX_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("UNICODE_SANDBOX_MEMORY_MB", "128")
    s2 = get_settings()
    assert s2.sandbox_timeout_seconds == 10
    assert s2.sandbox_memory_mb == 128

