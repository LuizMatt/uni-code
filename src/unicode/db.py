"""Database access: connection pool and explicit transactions.

Services receive a `DictConnection` as a parameter and never open transactions
themselves; the caller decides the transaction boundaries (see docs/architecture/database.md).
"""

from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Connection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

from unicode.config import get_settings

DictConnection = Connection[DictRow]
DictPool = ConnectionPool[DictConnection]

_pool: DictPool | None = None


def create_pool(conninfo: str, *, min_size: int = 1, max_size: int = 10) -> DictPool:
    """Create and open a pool whose connections return rows as dicts."""
    return ConnectionPool(
        conninfo,
        connection_class=DictConnection,
        kwargs={"row_factory": dict_row},
        min_size=min_size,
        max_size=max_size,
        open=True,
        name="unicode",
    )


def get_pool() -> DictPool:
    """Return the process-wide pool, creating it from Settings on first use.

    Not thread-safe on first call: the daemon must call it once at startup.
    """
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = create_pool(
            settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
        )
    return _pool


def close_pool() -> None:
    """Close the process-wide pool (no-op if it was never created)."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def transaction(pool: DictPool | None = None) -> Iterator[DictConnection]:
    """Borrow a connection and run the block in one transaction.

    COMMIT on normal exit; ROLLBACK and re-raise on exception.
    """
    with (pool or get_pool()).connection() as conn, conn.transaction():
        yield conn
