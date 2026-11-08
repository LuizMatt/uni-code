import pytest
from psycopg import errors

from unicode.db import DictConnection

pytestmark = pytest.mark.db

STUDENT = "INSERT INTO students (registration, email) VALUES ('00777', 'g@uni.edu')"


def _denied(conn: DictConnection, sql: str) -> None:
    with pytest.raises(errors.InsufficientPrivilege), conn.transaction():
        conn.execute(sql)


# --- daemon -------------------------------------------------------------------


def test_daemon_can_insert_update_select_domain_tables(daemon_conn: DictConnection) -> None:
    daemon_conn.execute(STUDENT)
    daemon_conn.execute("UPDATE students SET name = 'G' WHERE registration = '00777'")
    unit = daemon_conn.execute(
        "INSERT INTO units (code, title) VALUES ('unit-g', 'G') RETURNING id"
    ).fetchone()
    assert unit is not None
    daemon_conn.execute(
        "INSERT INTO questions (unit_id, slug, title) VALUES (%s, 'q-g', 'G')", (unit["id"],)
    )
    assert daemon_conn.execute("SELECT count(*) AS n FROM students").fetchone() == {"n": 1}


def test_daemon_cannot_delete_history(daemon_conn: DictConnection) -> None:
    daemon_conn.execute(STUDENT)
    _denied(daemon_conn, "DELETE FROM students")
    _denied(daemon_conn, "DELETE FROM assignments")
    _denied(daemon_conn, "DELETE FROM attempts")


def test_daemon_audit_log_is_append_only(daemon_conn: DictConnection) -> None:
    daemon_conn.execute("INSERT INTO audit_log (actor, action) VALUES ('admin', 'test')")
    _denied(daemon_conn, "UPDATE audit_log SET action = 'x'")
    _denied(daemon_conn, "DELETE FROM audit_log")


def test_daemon_can_delete_sessions(daemon_conn: DictConnection) -> None:
    daemon_conn.execute(STUDENT)
    daemon_conn.execute(
        "INSERT INTO sessions (token_hash, student_registration, expires_at) "
        "VALUES (sha256('t'), '00777', now() + interval '1 hour')"
    )
    daemon_conn.execute("DELETE FROM sessions")


def test_daemon_can_read_grades_view(daemon_conn: DictConnection) -> None:
    assert daemon_conn.execute("SELECT * FROM grades_by_unit").fetchall() == []


def test_daemon_cannot_create_tables(daemon_conn: DictConnection) -> None:
    _denied(daemon_conn, "CREATE TABLE hack (x int)")


# --- panel --------------------------------------------------------------------


def test_panel_can_read_grades_and_history(panel_conn: DictConnection) -> None:
    for relation in ("students", "units", "questions", "assignments", "attempts", "audit_log"):
        panel_conn.execute(f"SELECT 1 FROM {relation} LIMIT 1")
    panel_conn.execute("SELECT * FROM grades_by_unit")


def test_panel_cannot_write(panel_conn: DictConnection) -> None:
    _denied(panel_conn, STUDENT)
    _denied(panel_conn, "UPDATE students SET name = 'x'")
    _denied(panel_conn, "INSERT INTO audit_log (actor, action) VALUES ('panel', 'x')")


def test_panel_cannot_read_sessions(panel_conn: DictConnection) -> None:
    _denied(panel_conn, "SELECT * FROM sessions")
