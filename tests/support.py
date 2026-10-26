"""Shared constants for database tests (overridable via environment variables)."""

import os
from pathlib import Path

from alembic.config import Config

ROOT = Path(__file__).resolve().parent.parent

TEST_OWNER_URL = os.environ.get(
    "UNICODE_TEST_OWNER_URL",
    "postgresql://unicode_owner:unicode_owner@localhost:5432/unicode_test",
)
TEST_DAEMON_URL = os.environ.get(
    "UNICODE_TEST_DAEMON_URL",
    "postgresql://unicode_daemon:unicode_daemon@localhost:5432/unicode_test",
)
TEST_PANEL_URL = os.environ.get(
    "UNICODE_TEST_PANEL_URL",
    "postgresql://unicode_panel:unicode_panel@localhost:5432/unicode_test",
)


def alembic_config(url: str) -> Config:
    """Alembic config pointing at `url` (used by tests to migrate unicode_test)."""
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg
