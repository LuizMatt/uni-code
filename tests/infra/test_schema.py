from typing import Any

import psycopg
import pytest
from psycopg import errors

from unicode.db import DictConnection

pytestmark = pytest.mark.db


def _scalar(conn: DictConnection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    assert row is not None
    return next(iter(row.values()))


def _expect_error(
    conn: DictConnection, exc: type[psycopg.Error], sql: str, params: tuple[Any, ...] = ()
) -> None:
    # Nested transaction = SAVEPOINT, so the outer test transaction stays usable.
    with pytest.raises(exc), conn.transaction():
        conn.execute(sql, params)


@pytest.fixture
def seed(owner_conn: DictConnection) -> dict[str, Any]:
    conn = owner_conn
    unit_a = _scalar(conn, "INSERT INTO units (code, title) VALUES ('unit-01', 'U1') RETURNING id")
    unit_b = _scalar(conn, "INSERT INTO units (code, title) VALUES ('unit-02', 'U2') RETURNING id")
    q_a1 = _scalar(
        conn,
        "INSERT INTO questions (unit_id, slug, title) VALUES (%s, 'q-a1', 'A1') RETURNING id",
        (unit_a,),
    )
    q_a2 = _scalar(
        conn,
        "INSERT INTO questions (unit_id, slug, title) VALUES (%s, 'q-a2', 'A2') RETURNING id",
        (unit_a,),
    )
    q_b1 = _scalar(
        conn,
        "INSERT INTO questions (unit_id, slug, title) VALUES (%s, 'q-b1', 'B1') RETURNING id",
        (unit_b,),
    )
    conn.execute(
        "INSERT INTO students (registration, email, name) "
        "VALUES ('00123', 'aluno@uni.edu', 'Aluno')"
    )
    return {"unit_a": unit_a, "unit_b": unit_b, "q_a1": q_a1, "q_a2": q_a2, "q_b1": q_b1}


def _assign(
    conn: DictConnection, question_id: int, unit_id: int, state: str = "pending", points: float = 0
) -> int:
    return int(
        _scalar(
            conn,
            "INSERT INTO assignments (student_registration, question_id, unit_id, state, points) "
            "VALUES ('00123', %s, %s, %s, %s) RETURNING id",
            (question_id, unit_id, state, points),
        )
    )


# --- students -----------------------------------------------------------------


def test_registration_keeps_leading_zeros(owner_conn: DictConnection, seed: dict[str, Any]) -> None:
    assert _scalar(owner_conn, "SELECT registration FROM students") == "00123"


def test_registration_rejects_surrounding_whitespace(
    owner_conn: DictConnection, seed: dict[str, Any]
) -> None:
    _expect_error(
        owner_conn,
        errors.CheckViolation,
        "INSERT INTO students (registration, email) VALUES (' 00999 ', 'x@uni.edu')",
    )


def test_email_unique_case_insensitive(owner_conn: DictConnection, seed: dict[str, Any]) -> None:
    _expect_error(
        owner_conn,
        errors.UniqueViolation,
        "INSERT INTO students (registration, email) VALUES ('00999', 'ALUNO@UNI.EDU')",
    )


def test_cannot_delete_student_with_history(
    owner_conn: DictConnection, seed: dict[str, Any]
) -> None:
    _assign(owner_conn, seed["q_a1"], seed["unit_a"])
    _expect_error(
        owner_conn,
        errors.ForeignKeyViolation,
        "DELETE FROM students WHERE registration = '00123'",
    )


# --- identity -----------------------------------------------------------------


def test_identity_ids_cannot_be_set_manually(owner_conn: DictConnection) -> None:
    _expect_error(
        owner_conn,
        errors.GeneratedAlways,
        "INSERT INTO units (id, code, title) VALUES (999, 'unit-99', 'U99')",
    )


# --- assignments --------------------------------------------------------------


def test_assignment_question_must_belong_to_unit(
    owner_conn: DictConnection, seed: dict[str, Any]
) -> None:
    _expect_error(
        owner_conn,
        errors.ForeignKeyViolation,
        "INSERT INTO assignments (student_registration, question_id, unit_id) "
        "VALUES ('00123', %s, %s)",
        (seed["q_b1"], seed["unit_a"]),
    )


@pytest.mark.parametrize(("state", "points"), [("passed", 0), ("pending", 0.5), ("replaced", 0.5)])
def test_points_must_match_state(
    owner_conn: DictConnection, seed: dict[str, Any], state: str, points: float
) -> None:
    with pytest.raises(errors.CheckViolation), owner_conn.transaction():
        _assign(owner_conn, seed["q_a1"], seed["unit_a"], state, points)


def test_passed_with_half_point_is_valid(owner_conn: DictConnection, seed: dict[str, Any]) -> None:
    assignment_id = _assign(owner_conn, seed["q_a1"], seed["unit_a"], "passed", 0.5)
    assert assignment_id > 0


def test_only_one_non_replaced_assignment_per_question(
    owner_conn: DictConnection, seed: dict[str, Any]
) -> None:
    first = _assign(owner_conn, seed["q_a1"], seed["unit_a"])
    with pytest.raises(errors.UniqueViolation), owner_conn.transaction():
        _assign(owner_conn, seed["q_a1"], seed["unit_a"])

    owner_conn.execute("UPDATE assignments SET state = 'replaced' WHERE id = %s", (first,))
    assert _assign(owner_conn, seed["q_a1"], seed["unit_a"]) != first


def test_invalid_assignment_state_rejected(
    owner_conn: DictConnection, seed: dict[str, Any]
) -> None:
    with pytest.raises(errors.CheckViolation), owner_conn.transaction():
        _assign(owner_conn, seed["q_a1"], seed["unit_a"], "aprovada", 0)


# --- attempts -----------------------------------------------------------------


def _attempt(conn: DictConnection, assignment_id: int, number: int) -> None:
    conn.execute(
        "INSERT INTO attempts (assignment_id, number, code) VALUES (%s, %s, 'print(1)')",
        (assignment_id, number),
    )


def test_attempt_number_between_1_and_3(owner_conn: DictConnection, seed: dict[str, Any]) -> None:
    assignment_id = _assign(owner_conn, seed["q_a1"], seed["unit_a"])
    for n in (1, 2, 3):
        _attempt(owner_conn, assignment_id, n)
    with pytest.raises(errors.CheckViolation), owner_conn.transaction():
        _attempt(owner_conn, assignment_id, 4)


def test_attempt_number_unique_per_assignment(
    owner_conn: DictConnection, seed: dict[str, Any]
) -> None:
    assignment_id = _assign(owner_conn, seed["q_a1"], seed["unit_a"])
    _attempt(owner_conn, assignment_id, 1)
    with pytest.raises(errors.UniqueViolation), owner_conn.transaction():
        _attempt(owner_conn, assignment_id, 1)


def test_attempt_defaults_to_running(owner_conn: DictConnection, seed: dict[str, Any]) -> None:
    assignment_id = _assign(owner_conn, seed["q_a1"], seed["unit_a"])
    _attempt(owner_conn, assignment_id, 1)
    assert _scalar(owner_conn, "SELECT status FROM attempts") == "running"


def test_tests_passed_cannot_exceed_total(
    owner_conn: DictConnection, seed: dict[str, Any]
) -> None:
    assignment_id = _assign(owner_conn, seed["q_a1"], seed["unit_a"])
    _expect_error(
        owner_conn,
        errors.CheckViolation,
        "INSERT INTO attempts (assignment_id, number, code, tests_total, tests_passed) "
        "VALUES (%s, 1, 'x', 3, 4)",
        (assignment_id,),
    )


# --- sessions -----------------------------------------------------------------


def test_session_token_hash_must_be_32_bytes(
    owner_conn: DictConnection, seed: dict[str, Any]
) -> None:
    _expect_error(
        owner_conn,
        errors.CheckViolation,
        "INSERT INTO sessions (token_hash, student_registration, expires_at) "
        "VALUES (%s, '00123', now() + interval '1 hour')",
        (b"short",),
    )


def test_session_accepts_sha256_hash(owner_conn: DictConnection, seed: dict[str, Any]) -> None:
    owner_conn.execute(
        "INSERT INTO sessions (token_hash, student_registration, expires_at) "
        "VALUES (sha256('token'), '00123', now() + interval '1 hour')"
    )
    assert _scalar(owner_conn, "SELECT count(*) FROM sessions") == 1


# --- grades view ----------------------------------------------------------------


def test_grades_by_unit_sums_points_per_unit(
    owner_conn: DictConnection, seed: dict[str, Any]
) -> None:
    _assign(owner_conn, seed["q_a1"], seed["unit_a"], "passed", 0.5)
    _assign(owner_conn, seed["q_a2"], seed["unit_a"], "passed", 0.5)
    _assign(owner_conn, seed["q_b1"], seed["unit_b"], "exhausted", 0)

    rows = owner_conn.execute(
        "SELECT unit, points FROM grades_by_unit WHERE registration = '00123' ORDER BY unit"
    ).fetchall()

    assert [(r["unit"], float(r["points"])) for r in rows] == [("unit-01", 1.0), ("unit-02", 0.0)]


def test_grades_by_unit_ignores_replaced(owner_conn: DictConnection, seed: dict[str, Any]) -> None:
    _assign(owner_conn, seed["q_a1"], seed["unit_a"], "replaced", 0)
    rows = owner_conn.execute("SELECT * FROM grades_by_unit").fetchall()
    assert rows == []
