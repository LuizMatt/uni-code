from pathlib import Path

import pytest

from unicode.config import Settings, get_settings


def test_settings_default_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UNICODE_DATABASE_URL", raising=False)
    monkeypatch.delenv("UNICODE_QUESTIONS_DIR", raising=False)
    monkeypatch.delenv("UNICODE_WORKSPACES_DIR", raising=False)
    monkeypatch.delenv("UNICODE_DAEMON_SOCKET_PATH", raising=False)
    monkeypatch.delenv("UNICODE_ADMIN_PASSWORD", raising=False)

    settings = Settings(_env_file=None)

    assert (
        settings.database_url
        == "postgresql://unicode_daemon:unicode_daemon@localhost:5432/unicode"
    )
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
