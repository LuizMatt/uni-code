import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from tests.support import ROOT, TEST_DAEMON_URL, TEST_OWNER_URL
from unicode.db import DictConnection
from unicode.models.sandbox import SandboxResult
from unicode.services.assignments import draw_assignments, reset_assignments
from unicode.services.submissions import (
    AssignmentAlreadyClosedError,
    AssignmentNotFoundError,
    AttemptInProgressError,
    EmptySubmissionError,
    MaxAttemptsReachedError,
    QuestionTestNotFoundError,
    SubmissionError,
    finalize_attempt,
    list_attempts,
    recover_stale_attempts,
    reserve_attempt,
    submit_solution,
)


class FakeCursor:
    def __init__(
        self,
        fetchone_val: dict[str, Any] | None = None,
        fetchall_val: list[dict[str, Any]] | None = None,
    ) -> None:
        self._fetchone_val = fetchone_val
        self._fetchall_val = fetchall_val or []

    def fetchone(self) -> dict[str, Any] | None:
        return self._fetchone_val

    def fetchall(self) -> list[dict[str, Any]]:
        return self._fetchall_val


class FakeSubmissionConn:
    """In-memory fake connection to test Phase A, Phase C, and recovery logic offline."""

    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.assignments: dict[int, dict[str, Any]] = {
            1: {
                "id": 1,
                "student_registration": "2026001",
                "unit_id": 10,
                "unit_code": "unit-01",
                "question_id": 100,
                "question_slug": "soma-dois-numeros",
                "round": 1,
                "state": "pending",
                "points": Decimal("0.0"),
                "created_at": now,
            }
        }
        self.attempts: dict[int, dict[str, Any]] = {}
        self.audit_logs: list[dict[str, Any]] = []
        self._next_attempt_id = 1

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> FakeCursor:
        norm = " ".join(sql.split())

        # Phase A: find active assignment FOR UPDATE OF a
        if (
            "FROM assignments a" in norm
            and "WHERE a.student_registration = %s AND u.code = %s AND q.slug = %s" in norm
            and "FOR UPDATE OF a" in norm
        ):
            reg, u_code, q_slug = str(params[0]), str(params[1]), str(params[2])
            for a in self.assignments.values():
                if (
                    a["student_registration"] == reg
                    and a["unit_code"] == u_code
                    and a["question_slug"] == q_slug
                    and a["state"] != "replaced"
                ):
                    return FakeCursor(fetchone_val=dict(a))
            return FakeCursor(fetchone_val=None)

        # List attempts for assignment
        if "FROM attempts WHERE assignment_id = %s ORDER BY number" in norm:
            aid = int(params[0])
            rows = [
                dict(att)
                for att in sorted(self.attempts.values(), key=lambda x: int(x["number"]))
                if att["assignment_id"] == aid
            ]
            return FakeCursor(fetchall_val=rows)

        # Insert attempt
        if "INSERT INTO attempts" in norm:
            aid, num, code = int(params[0]), int(params[1]), str(params[2])
            att_id = self._next_attempt_id
            self._next_attempt_id += 1
            now = datetime.now(UTC)
            rec = {
                "id": att_id,
                "assignment_id": aid,
                "number": num,
                "status": "running",
                "tests_total": None,
                "tests_passed": None,
                "output": None,
                "code": code,
                "started_at": now,
                "finished_at": None,
            }
            self.attempts[att_id] = rec
            return FakeCursor(fetchone_val=dict(rec))

        # Phase C: select attempt + assignment FOR UPDATE OF att, a
        if (
            "FROM attempts att JOIN assignments a ON a.id = att.assignment_id" in norm
            and "WHERE att.id = %s FOR UPDATE OF att, a" in norm
        ):
            att_id = int(params[0])
            att = self.attempts.get(att_id)
            if att is None:
                return FakeCursor(fetchone_val=None)
            a = self.assignments[int(att["assignment_id"])]
            combined = {
                **a,
                "attempt_id": att["id"],
                "assignment_id": att["assignment_id"],
                "number": att["number"],
                "attempt_status": att["status"],
                "code": att["code"],
                "started_at": att["started_at"],
            }
            return FakeCursor(fetchone_val=combined)

        # Recover stale attempts select
        if (
            "FROM attempts att JOIN assignments a ON a.id = att.assignment_id" in norm
            and "WHERE att.status = 'running'" in norm
        ):
            rows = []
            for att in sorted(self.attempts.values(), key=lambda x: int(x["id"])):
                if att["status"] == "running":
                    a = self.assignments[int(att["assignment_id"])]
                    rows.append(
                        {
                            "attempt_id": att["id"],
                            "assignment_id": att["assignment_id"],
                            "number": att["number"],
                            "assignment_state": a["state"],
                        }
                    )
            return FakeCursor(fetchall_val=rows)

        # Update attempt
        if "UPDATE attempts SET status = %s" in norm:
            status, total, passed, output, att_id = (
                str(params[0]),
                int(params[1]),
                int(params[2]),
                str(params[3]),
                int(params[4]),
            )
            att = self.attempts[att_id]
            att["status"] = status
            att["tests_total"] = total
            att["tests_passed"] = passed
            att["output"] = output
            att["finished_at"] = datetime.now(UTC)
            return FakeCursor(fetchone_val=dict(att))

        # Update assignment state & points
        if "UPDATE assignments SET state = %s, points = %s WHERE id = %s" in norm:
            new_state, new_pts, aid = str(params[0]), Decimal(str(params[1])), int(params[2])
            self.assignments[aid]["state"] = new_state
            self.assignments[aid]["points"] = new_pts
            return FakeCursor()

        # Audit log
        if "INSERT INTO audit_log" in norm:
            self.audit_logs.append(
                {
                    "actor": params[0],
                    "action": params[1],
                    "details": json.loads(str(params[2])),
                }
            )
            return FakeCursor()

        raise AssertionError(f"Unexpected SQL in FakeSubmissionConn: {norm}")


class FakeRunner:
    def __init__(self, results: list[SandboxResult] | Exception) -> None:
        self._results = results
        self.calls: list[tuple[str, Path]] = []

    def run(self, code: str, test_eval_path: Path) -> SandboxResult:
        self.calls.append((code, test_eval_path))
        if isinstance(self._results, Exception):
            raise self._results
        return self._results.pop(0)


def test_offline_three_failures_exhausts_assignment() -> None:
    conn = FakeSubmissionConn()
    db_conn: DictConnection = conn  # type: ignore[assignment]

    fail_res = SandboxResult(
        outcome="failed",
        tests_total=3,
        tests_passed=2,
        first_failed_test="test_soma_com_negativos",
        diagnostic_output="[test_soma_com_negativos] assert 0 == -10",
    )

    for expected_num, expected_rem, expected_state in [
        (1, 2, "pending"),
        (2, 1, "pending"),
        (3, 0, "exhausted"),
    ]:
        reserved = reserve_attempt(
            db_conn, "2026001", "unit-01", "soma-dois-numeros", "def soma(a,b): return 0"
        )
        assert reserved.attempt.number == expected_num
        assert reserved.attempt.status == "running"

        sub = finalize_attempt(db_conn, reserved.attempt.id, fail_res)
        assert sub.attempt.status == "failed"
        assert sub.attempt.output == "[test_soma_com_negativos] assert 0 == -10"
        assert sub.assignment.state == expected_state
        assert sub.assignment.points == Decimal("0.0")
        assert sub.feedback.status == "failed"
        assert sub.feedback.tests_total == 3
        assert sub.feedback.tests_passed == 2
        assert sub.feedback.attempt_number == expected_num
        assert sub.feedback.attempts_remaining == expected_rem
        assert sub.feedback.first_failed_test == "test_soma_com_negativos"

    with pytest.raises(AssignmentAlreadyClosedError, match="esgotado"):
        reserve_attempt(
            db_conn, "2026001", "unit-01", "soma-dois-numeros", "def soma(a,b): return a+b"
        )


def test_offline_approval_on_second_attempt_awards_half_point_and_locks() -> None:
    conn = FakeSubmissionConn()
    db_conn: DictConnection = conn  # type: ignore[assignment]

    r1 = reserve_attempt(
        db_conn, "2026001", "unit-01", "soma-dois-numeros", "def soma(a,b): return 0"
    )
    finalize_attempt(
        db_conn,
        r1.attempt.id,
        SandboxResult(outcome="failed", tests_total=3, tests_passed=1),
    )

    r2 = reserve_attempt(
        db_conn, "2026001", "unit-01", "soma-dois-numeros", "def soma(a,b): return a+b"
    )
    sub2 = finalize_attempt(
        db_conn,
        r2.attempt.id,
        SandboxResult(
            outcome="passed",
            tests_total=3,
            tests_passed=3,
            diagnostic_output="3 passed",
        ),
    )
    assert sub2.attempt.number == 2
    assert sub2.attempt.status == "passed"
    assert sub2.assignment.state == "passed"
    assert sub2.assignment.points == Decimal("0.5")
    assert sub2.feedback.attempts_remaining == 0
    assert sub2.feedback.points == Decimal("0.5")

    with pytest.raises(AssignmentAlreadyClosedError, match="aprovada"):
        reserve_attempt(
            db_conn, "2026001", "unit-01", "soma-dois-numeros", "def soma(a,b): return a+b"
        )


def test_offline_validation_and_in_progress_guard() -> None:
    conn = FakeSubmissionConn()
    db_conn: DictConnection = conn  # type: ignore[assignment]

    with pytest.raises(EmptySubmissionError):
        reserve_attempt(db_conn, "2026001", "unit-01", "soma-dois-numeros", "   \n  ")

    with pytest.raises(AssignmentNotFoundError):
        reserve_attempt(db_conn, "2026001", "unit-01", "questao-nao-sorteada", "x = 1")

    r1 = reserve_attempt(db_conn, "2026001", "unit-01", "soma-dois-numeros", "x = 1")
    assert r1.attempt.status == "running"

    with pytest.raises(AttemptInProgressError):
        reserve_attempt(db_conn, "2026001", "unit-01", "soma-dois-numeros", "x = 2")

    # If assignment is pending but already has 3 attempts
    for i in range(1, 4):
        conn.attempts[i] = {
            "id": i,
            "assignment_id": 1,
            "number": i,
            "status": "failed",
            "tests_total": 3,
            "tests_passed": 0,
            "output": "",
            "code": "x = 1",
            "started_at": datetime.now(UTC),
            "finished_at": datetime.now(UTC),
        }
    with pytest.raises(MaxAttemptsReachedError):
        reserve_attempt(db_conn, "2026001", "unit-01", "soma-dois-numeros", "x = 9")


def test_offline_finalize_attempt_requires_running_status() -> None:
    conn = FakeSubmissionConn()
    db_conn: DictConnection = conn  # type: ignore[assignment]

    r = reserve_attempt(db_conn, "2026001", "unit-01", "soma-dois-numeros", "x = 1")
    res = SandboxResult(outcome="passed", tests_total=3, tests_passed=3)
    finalize_attempt(db_conn, r.attempt.id, res)

    # Calling finalize_attempt again on the now-passed attempt must fail
    with pytest.raises(SubmissionError, match="não está em execução"):
        finalize_attempt(db_conn, r.attempt.id, res)


def test_offline_recover_stale_attempts_and_third_attempt_exhaustion() -> None:
    conn = FakeSubmissionConn()
    db_conn: DictConnection = conn  # type: ignore[assignment]

    # Attempts 1 and 2 failed normally
    for _ in range(2):
        r = reserve_attempt(db_conn, "2026001", "unit-01", "soma-dois-numeros", "x = 1")
        finalize_attempt(
            db_conn,
            r.attempt.id,
            SandboxResult(outcome="failed", tests_total=3, tests_passed=0),
        )

    # Attempt 3 crashes during Phase B (remains 'running')
    r3 = reserve_attempt(db_conn, "2026001", "unit-01", "soma-dois-numeros", "x = 3")
    assert r3.attempt.number == 3
    assert conn.assignments[1]["state"] == "pending"

    recovered = recover_stale_attempts(db_conn)
    assert len(recovered) == 1
    assert recovered[0].id == r3.attempt.id
    assert recovered[0].status == "error"
    assert conn.assignments[1]["state"] == "exhausted"
    assert conn.assignments[1]["points"] == Decimal("0.0")
    assert conn.audit_logs[-1]["action"] == "recover_stale_attempts"


def test_offline_submit_solution_orchestrator_handles_runner_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeSubmissionConn()
    db_conn: DictConnection = conn  # type: ignore[assignment]

    @contextmanager
    def fake_tx(_pool: Any = None) -> Iterator[DictConnection]:
        yield db_conn

    monkeypatch.setattr("unicode.services.submissions.transaction", fake_tx)

    runner = FakeRunner(RuntimeError("Docker socket unreachable"))
    result = submit_solution(
        "2026001",
        "unit-01",
        "soma-dois-numeros",
        "def soma(a, b): return a + b\n",
        questions_dir=ROOT / "questions",
        runner=runner,
    )
    assert result.attempt.status == "error"
    assert result.feedback.status == "error"
    assert result.feedback.error_category == "SandboxError"
    assert result.feedback.attempts_remaining == 2

    with pytest.raises(QuestionTestNotFoundError):
        submit_solution(
            "2026001",
            "unit-01",
            "inexistente",
            "x = 1",
            questions_dir=ROOT / "questions",
            runner=runner,
        )


def _seed_db_student_and_unit(conn: DictConnection) -> None:
    with psycopg.connect(TEST_OWNER_URL, row_factory=dict_row) as owner:
        with owner.transaction():
            owner.execute("DELETE FROM audit_log")
            owner.execute("DELETE FROM attempts")
            owner.execute("DELETE FROM assignments")
            owner.execute("DELETE FROM questions")
            owner.execute("DELETE FROM units")
            owner.execute("DELETE FROM students")

    conn.execute(
        "INSERT INTO students (registration, email, name, class_group) "
        "VALUES ('2026001', 'aluno1@uni.edu', 'Aluno 1', 'T01')"
    )
    unit_row = conn.execute(
        "INSERT INTO units (code, title) VALUES ('unit-01', 'Unidade 1') RETURNING id"
    ).fetchone()
    assert unit_row is not None
    uid = int(unit_row["id"])
    for slug in (
        "soma-dois-numeros",
        "eh-par",
        "fatorial",
        "maior-de-tres",
        "inverter-string",
    ):
        conn.execute(
            "INSERT INTO questions (unit_id, slug, title, active) VALUES (%s, %s, %s, TRUE)",
            (uid, slug, slug),
        )


@pytest.mark.db
def test_db_submission_lifecycle_and_grades_view(migrated_db: None) -> None:
    try:
        with psycopg.connect(TEST_DAEMON_URL, row_factory=dict_row) as conn:
            with conn.transaction():
                _seed_db_student_and_unit(conn)
                draw = draw_assignments(conn, "2026001", "unit-01")
                q1_slug = draw.assignments[0].question_slug
                q2_slug = draw.assignments[1].question_slug

                # Q1: fail 1st, pass 2nd
                r1 = reserve_attempt(conn, "2026001", "unit-01", q1_slug, "x = 1")
                finalize_attempt(
                    conn,
                    r1.attempt.id,
                    SandboxResult(outcome="failed", tests_total=3, tests_passed=1),
                )
                r2 = reserve_attempt(conn, "2026001", "unit-01", q1_slug, "x = 2")
                sub_q1 = finalize_attempt(
                    conn,
                    r2.attempt.id,
                    SandboxResult(outcome="passed", tests_total=3, tests_passed=3),
                )
                assert sub_q1.assignment.state == "passed"
                assert sub_q1.assignment.points == Decimal("0.5")

                # Q2: fail all 3 -> exhausted
                for _ in range(3):
                    rq = reserve_attempt(conn, "2026001", "unit-01", q2_slug, "x = 0")
                    sub_q2 = finalize_attempt(
                        conn,
                        rq.attempt.id,
                        SandboxResult(outcome="failed", tests_total=3, tests_passed=0),
                    )
                assert sub_q2.assignment.state == "exhausted"
                assert sub_q2.assignment.points == Decimal("0.0")
                assert len(list_attempts(conn, sub_q2.assignment.id)) == 3

                grade_row = conn.execute(
                    "SELECT points FROM grades_by_unit "
                    "WHERE registration = '2026001' AND unit = 'unit-01'"
                ).fetchone()
                assert grade_row is not None
                assert Decimal(str(grade_row["points"])) == Decimal("0.5")
    finally:
        with psycopg.connect(TEST_OWNER_URL, row_factory=dict_row) as owner:
            with owner.transaction():
                owner.execute("DELETE FROM audit_log")
                owner.execute("DELETE FROM attempts")
                owner.execute("DELETE FROM assignments")
                owner.execute("DELETE FROM questions")
                owner.execute("DELETE FROM units")
                owner.execute("DELETE FROM students")


@pytest.mark.db
def test_db_concurrent_submissions_and_reset_during_phase_b(migrated_db: None) -> None:
    try:
        with psycopg.connect(TEST_DAEMON_URL, row_factory=dict_row) as setup_conn:
            with setup_conn.transaction():
                _seed_db_student_and_unit(setup_conn)
                draw = draw_assignments(setup_conn, "2026001", "unit-01")
                target_slug = draw.assignments[0].question_slug

        # 1. Two concurrent Phase A reservations: exactly one succeeds,
        # the other gets AttemptInProgressError
        def worker_reserve(idx: int) -> str:
            with psycopg.connect(TEST_DAEMON_URL, row_factory=dict_row) as w_conn:
                with w_conn.transaction():
                    try:
                        reserve_attempt(
                            w_conn, "2026001", "unit-01", target_slug, f"code_{idx}"
                        )
                        return "reserved"
                    except AttemptInProgressError:
                        return "in_progress"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = sorted(pool.map(worker_reserve, [1, 2]))
        assert outcomes == ["in_progress", "reserved"]

        # 2. Admin resets the assignment while attempt #1 is still 'running', then Phase C finishes
        with psycopg.connect(TEST_DAEMON_URL, row_factory=dict_row) as conn:
            with conn.transaction():
                att_row = conn.execute("SELECT id FROM attempts LIMIT 1").fetchone()
                assert att_row is not None
                att_id = int(att_row["id"])

                reset_assignments(conn, "2026001", "unit-01", question_slug=target_slug)
                res = finalize_attempt(
                    conn,
                    att_id,
                    SandboxResult(outcome="passed", tests_total=3, tests_passed=3),
                )
                # The attempt is recorded as passed, but the replaced
                # assignment remains 'replaced' with 0 points
                assert res.attempt.status == "passed"
                assert res.assignment.state == "replaced"
                assert res.assignment.points == Decimal("0.0")
    finally:
        with psycopg.connect(TEST_OWNER_URL, row_factory=dict_row) as owner:
            with owner.transaction():
                owner.execute("DELETE FROM audit_log")
                owner.execute("DELETE FROM attempts")
                owner.execute("DELETE FROM assignments")
                owner.execute("DELETE FROM questions")
                owner.execute("DELETE FROM units")
                owner.execute("DELETE FROM students")
