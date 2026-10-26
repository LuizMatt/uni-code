"""Shared fixtures. Database tests use the docker-compose Postgres (database unicode_test)."""

from collections.abc import Iterator

import psycopg
import pytest
from alembic import command
from psycopg.rows import dict_row

from tests.support import TEST_DAEMON_URL, TEST_OWNER_URL, TEST_PANEL_URL, alembic_config
from unicode.db import DictConnection


@pytest.fixture(scope="session")
def database_available() -> None:
    try:
        with psycopg.connect(TEST_OWNER_URL, connect_timeout=2):
            pass
    except psycopg.OperationalError as exc:
        pytest.skip(
            f"Postgres de teste indisponível ({exc}). Rode: docker compose up -d --wait"
        )


@pytest.fixture(scope="session")
def migrated_db(database_available: None) -> None:
    """Rebuild unicode_test from scratch once per test session."""
    cfg = alembic_config(TEST_OWNER_URL)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


def rollback_connection(url: str) -> Iterator[DictConnection]:
    """Yield a connection inside a transaction that is always rolled back."""
    with (
        psycopg.connect(url, row_factory=dict_row) as conn,
        conn.transaction(force_rollback=True),
    ):
        yield conn


@pytest.fixture
def owner_conn(migrated_db: None) -> Iterator[DictConnection]:
    yield from rollback_connection(TEST_OWNER_URL)


@pytest.fixture
def daemon_conn(migrated_db: None) -> Iterator[DictConnection]:
    yield from rollback_connection(TEST_DAEMON_URL)


@pytest.fixture
def panel_conn(migrated_db: None) -> Iterator[DictConnection]:
    yield from rollback_connection(TEST_PANEL_URL)
