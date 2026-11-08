import psycopg
import pytest
from alembic import command

from tests.support import TEST_OWNER_URL, alembic_config

pytestmark = pytest.mark.db

EXPECTED_TABLES = {
    "students",
    "units",
    "questions",
    "assignments",
    "attempts",
    "sessions",
    "audit_log",
}


def _relations(kind: str) -> set[str]:
    with psycopg.connect(TEST_OWNER_URL) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = %s",
            (kind,),
        ).fetchall()
    return {row[0] for row in rows} - {"alembic_version"}


def test_upgrade_creates_all_tables_and_view(migrated_db: None) -> None:
    assert _relations("BASE TABLE") == EXPECTED_TABLES
    assert _relations("VIEW") == {"grades_by_unit"}


def test_downgrade_to_base_then_upgrade_again(migrated_db: None) -> None:
    cfg = alembic_config(TEST_OWNER_URL)

    command.downgrade(cfg, "base")
    assert _relations("BASE TABLE") == set()
    assert _relations("VIEW") == set()

    command.upgrade(cfg, "head")
    assert _relations("BASE TABLE") == EXPECTED_TABLES
    assert _relations("VIEW") == {"grades_by_unit"}
