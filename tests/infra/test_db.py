from collections.abc import Iterator

import pytest

from tests.support import TEST_OWNER_URL
from unicode.db import DictPool, close_pool, create_pool, get_pool, transaction

pytestmark = pytest.mark.db


@pytest.fixture
def pool(database_available: None) -> Iterator[DictPool]:
    # max_size=1 guarantees the same connection, so TEMP tables survive between checkouts.
    p = create_pool(TEST_OWNER_URL, min_size=1, max_size=1)
    try:
        yield p
    finally:
        p.close()


def test_rows_are_dicts(pool: DictPool) -> None:
    with transaction(pool) as conn:
        row = conn.execute("SELECT 1 AS one").fetchone()
    assert row == {"one": 1}


def test_transaction_commits_on_success(pool: DictPool) -> None:
    with transaction(pool) as conn:
        conn.execute("CREATE TEMP TABLE t (x int)")
        conn.execute("INSERT INTO t VALUES (1)")
    with transaction(pool) as conn:
        row = conn.execute("SELECT count(*) AS n FROM t").fetchone()
    assert row == {"n": 1}


def test_transaction_rolls_back_on_exception(pool: DictPool) -> None:
    with transaction(pool) as conn:
        conn.execute("CREATE TEMP TABLE t (x int)")
    with pytest.raises(RuntimeError, match="boom"), transaction(pool) as conn:
        conn.execute("INSERT INTO t VALUES (1)")
        raise RuntimeError("boom")
    with transaction(pool) as conn:
        row = conn.execute("SELECT count(*) AS n FROM t").fetchone()
    assert row == {"n": 0}


def test_get_pool_is_singleton_built_from_settings(
    monkeypatch: pytest.MonkeyPatch, database_available: None
) -> None:
    monkeypatch.setenv("UNICODE_DATABASE_URL", TEST_OWNER_URL)
    close_pool()
    try:
        first = get_pool()
        assert first is get_pool()
        assert first.conninfo == TEST_OWNER_URL
        with transaction() as conn:
            assert conn.execute("SELECT 1 AS one").fetchone() == {"one": 1}
    finally:
        close_pool()


def test_close_pool_allows_recreation(
    monkeypatch: pytest.MonkeyPatch, database_available: None
) -> None:
    monkeypatch.setenv("UNICODE_DATABASE_URL", TEST_OWNER_URL)
    close_pool()
    first = get_pool()
    close_pool()
    try:
        assert get_pool() is not first
    finally:
        close_pool()
