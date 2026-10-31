import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from psycopg_pool import ConnectionPool

from unicode.config import get_settings
from unicode.db import DictConnection, transaction
from unicode.models.assignment import Assignment, AssignmentState
from unicode.models.attempt import (
    Attempt,
    AttemptStatus,
    FeedbackStatus,
    ReservedAttempt,
    StudentFeedback,
    SubmissionResult,
)
from unicode.models.sandbox import SandboxResult
from unicode.sandbox.runner import DockerSandboxRunner, SandboxRunner

_MAX_ATTEMPTS = 3


class SubmissionError(Exception):
    """Base exception for submission errors."""


class EmptySubmissionError(SubmissionError):
    """Raised when submitted code is empty or whitespace-only."""


class AssignmentNotFoundError(SubmissionError):
    """Raised when the student has no active assignment for the unit/question."""


class AssignmentAlreadyClosedError(SubmissionError):
    """Raised when the assignment is already passed or exhausted."""


class AttemptInProgressError(SubmissionError):
    """Raised when another attempt for the same assignment is currently running."""


class MaxAttemptsReachedError(SubmissionError):
    """Raised when the assignment already has 3 attempts."""


class QuestionTestNotFoundError(SubmissionError):
    """Raised when the question's test_eval.py file does not exist on disk."""


def _row_to_assignment(row: dict[str, Any]) -> Assignment:
    return Assignment(
        id=int(row["id"]),
        student_registration=str(row["student_registration"]),
        unit_id=int(row["unit_id"]),
        unit_code=str(row["unit_code"]),
        question_id=int(row["question_id"]),
        question_slug=str(row["question_slug"]),
        round=int(row["round"]),
        state=cast(AssignmentState, str(row["state"])),
        points=Decimal(str(row["points"])),
        created_at=cast(datetime, row["created_at"]),
    )


def _row_to_attempt(row: dict[str, Any]) -> Attempt:
    return Attempt(
        id=int(row["id"]),
        assignment_id=int(row["assignment_id"]),
        number=int(row["number"]),
        status=cast(AttemptStatus, str(row["status"])),
        code=str(row["code"]),
        started_at=cast(datetime, row["started_at"]),
        tests_total=int(row["tests_total"]) if row.get("tests_total") is not None else None,
        tests_passed=int(row["tests_passed"]) if row.get("tests_passed") is not None else None,
        output=str(row["output"]) if row.get("output") is not None else None,
        finished_at=cast(datetime | None, row.get("finished_at")),
    )


def list_attempts(conn: DictConnection, assignment_id: int) -> list[Attempt]:
    """Return all attempts for an assignment ordered by attempt number."""
    rows = conn.execute(
        "SELECT id, assignment_id, number, status, tests_total, tests_passed, "
        "output, code, started_at, finished_at "
        "FROM attempts WHERE assignment_id = %s ORDER BY number",
        (assignment_id,),
    ).fetchall()
    return [_row_to_attempt(r) for r in rows]


def reserve_attempt(
    conn: DictConnection,
    registration: str,
    unit_code: str,
    question_slug: str,
    code: str,
) -> ReservedAttempt:
    """Phase A: Lock active assignment, validate eligibility, and insert a 'running' attempt."""
    if not code or not code.strip():
        raise EmptySubmissionError("código da submissão não pode ser vazio")

    row = conn.execute(
        "SELECT a.id, a.student_registration, a.unit_id, u.code AS unit_code, "
        "a.question_id, q.slug AS question_slug, a.round, a.state, a.points, a.created_at "
        "FROM assignments a "
        "JOIN questions q ON q.id = a.question_id "
        "JOIN units u ON u.id = a.unit_id "
        "WHERE a.student_registration = %s AND u.code = %s AND q.slug = %s "
        "AND a.state <> 'replaced' "
        "FOR UPDATE OF a",
        (registration, unit_code, question_slug),
    ).fetchone()

    if row is None:
        raise AssignmentNotFoundError(
            f"nenhum sorteio ativo encontrado para o aluno '{registration}' "
            f"na questão '{question_slug}' da unidade '{unit_code}'"
        )

    assignment = _row_to_assignment(row)

    if assignment.state == "passed":
        raise AssignmentAlreadyClosedError(
            f"questão '{question_slug}' já foi aprovada"
        )
    if assignment.state == "exhausted":
        raise AssignmentAlreadyClosedError(
            f"limite de {_MAX_ATTEMPTS} tentativas já esgotado para a questão '{question_slug}'"
        )

    existing_attempts = conn.execute(
        "SELECT id, assignment_id, number, status, tests_total, tests_passed, "
        "output, code, started_at, finished_at "
        "FROM attempts WHERE assignment_id = %s ORDER BY number",
        (assignment.id,),
    ).fetchall()

    if any(str(att["status"]) == "running" for att in existing_attempts):
        raise AttemptInProgressError(
            f"já existe uma submissão em execução para a questão '{question_slug}'"
        )

    if len(existing_attempts) >= _MAX_ATTEMPTS:
        raise MaxAttemptsReachedError(
            f"limite de {_MAX_ATTEMPTS} tentativas já atingido para a questão '{question_slug}'"
        )

    next_number = len(existing_attempts) + 1
    inserted = conn.execute(
        "INSERT INTO attempts (assignment_id, number, status, code) "
        "VALUES (%s, %s, 'running', %s) "
        "RETURNING id, assignment_id, number, status, tests_total, tests_passed, "
        "output, code, started_at, finished_at",
        (assignment.id, next_number, code),
    ).fetchone()
    assert inserted is not None

    return ReservedAttempt(
        attempt=_row_to_attempt(inserted),
        assignment=assignment,
    )


def finalize_attempt(
    conn: DictConnection,
    attempt_id: int,
    sandbox_result: SandboxResult,
    *,
    actor: str | None = None,
) -> SubmissionResult:
    """Phase C: Record attempt result, update assignment state/points, and write audit_log."""
    joined = conn.execute(
        "SELECT att.id AS attempt_id, att.assignment_id, att.number, "
        "att.status AS attempt_status, att.code, att.started_at, "
        "a.id, a.student_registration, a.unit_id, u.code AS unit_code, "
        "a.question_id, q.slug AS question_slug, a.round, a.state, a.points, a.created_at "
        "FROM attempts att "
        "JOIN assignments a ON a.id = att.assignment_id "
        "JOIN questions q ON q.id = a.question_id "
        "JOIN units u ON u.id = a.unit_id "
        "WHERE att.id = %s FOR UPDATE OF att, a",
        (attempt_id,),
    ).fetchone()

    if joined is None:
        raise SubmissionError(f"tentativa '{attempt_id}' não encontrada")

    if str(joined["attempt_status"]) != "running":
        raise SubmissionError(
            f"tentativa '{attempt_id}' não está em execução (status: {joined['attempt_status']})"
        )

    tests_total = max(0, int(sandbox_result.tests_total))
    tests_passed = max(0, min(int(sandbox_result.tests_passed), tests_total))

    if (
        sandbox_result.outcome == "passed"
        and tests_total > 0
        and tests_passed == tests_total
    ):
        final_status: FeedbackStatus = "passed"
    elif sandbox_result.outcome == "failed" and tests_total > 0:
        final_status = "failed"
    else:
        final_status = "error"

    updated_att_row = conn.execute(
        "UPDATE attempts "
        "SET status = %s, tests_total = %s, tests_passed = %s, "
        "output = %s, finished_at = now() "
        "WHERE id = %s "
        "RETURNING id, assignment_id, number, status, tests_total, tests_passed, "
        "output, code, started_at, finished_at",
        (
            final_status,
            tests_total,
            tests_passed,
            sandbox_result.diagnostic_output,
            attempt_id,
        ),
    ).fetchone()
    assert updated_att_row is not None
    updated_attempt = _row_to_attempt(updated_att_row)

    current_assignment = _row_to_assignment(joined)
    new_state: AssignmentState = current_assignment.state
    new_points: Decimal = current_assignment.points

    if current_assignment.state == "pending":
        if final_status == "passed":
            new_state = "passed"
            new_points = Decimal("0.5")
            conn.execute(
                "UPDATE assignments SET state = %s, points = %s WHERE id = %s",
                (new_state, new_points, current_assignment.id),
            )
        elif updated_attempt.number >= _MAX_ATTEMPTS:
            new_state = "exhausted"
            new_points = Decimal("0.0")
            conn.execute(
                "UPDATE assignments SET state = %s, points = %s WHERE id = %s",
                (new_state, new_points, current_assignment.id),
            )

    updated_assignment = Assignment(
        id=current_assignment.id,
        student_registration=current_assignment.student_registration,
        unit_id=current_assignment.unit_id,
        unit_code=current_assignment.unit_code,
        question_id=current_assignment.question_id,
        question_slug=current_assignment.question_slug,
        round=current_assignment.round,
        state=new_state,
        points=new_points,
        created_at=current_assignment.created_at,
    )

    if new_state in ("passed", "exhausted", "replaced"):
        attempts_remaining = 0
    else:
        attempts_remaining = max(0, _MAX_ATTEMPTS - updated_attempt.number)

    audit_details = {
        "student_registration": updated_assignment.student_registration,
        "unit_code": updated_assignment.unit_code,
        "question_slug": updated_assignment.question_slug,
        "assignment_id": updated_assignment.id,
        "attempt_id": updated_attempt.id,
        "attempt_number": updated_attempt.number,
        "attempt_status": final_status,
        "tests_passed": tests_passed,
        "tests_total": tests_total,
        "assignment_state": new_state,
        "points": str(new_points),
    }
    conn.execute(
        "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
        (
            actor or updated_assignment.student_registration,
            "submit_attempt",
            json.dumps(audit_details),
        ),
    )

    feedback = StudentFeedback(
        status=final_status,
        tests_total=tests_total,
        tests_passed=tests_passed,
        attempt_number=updated_attempt.number,
        attempts_remaining=attempts_remaining,
        assignment_state=new_state,
        points=new_points,
        first_failed_test=sandbox_result.first_failed_test if final_status == "failed" else None,
        error_category=sandbox_result.error_category if final_status == "error" else None,
    )

    return SubmissionResult(
        attempt=updated_attempt,
        assignment=updated_assignment,
        feedback=feedback,
    )


def submit_solution(
    registration: str,
    unit_code: str,
    question_slug: str,
    code: str,
    *,
    questions_dir: Path | None = None,
    runner: SandboxRunner | None = None,
    pool: ConnectionPool[DictConnection] | None = None,
    actor: str | None = None,
) -> SubmissionResult:
    """Orchestrate Phase A, Phase B (sandbox outside DB tx), and Phase C (finalize)."""
    q_dir = questions_dir if questions_dir is not None else get_settings().questions_dir
    test_eval_path = q_dir / unit_code / question_slug / "test_eval.py"
    if not test_eval_path.exists() or not test_eval_path.is_file():
        raise QuestionTestNotFoundError(
            f"arquivo de avaliação não encontrado para '{unit_code}/{question_slug}'"
        )

    with transaction(pool) as conn:
        reserved = reserve_attempt(conn, registration, unit_code, question_slug, code)

    active_runner: SandboxRunner = runner if runner is not None else DockerSandboxRunner()
    try:
        sandbox_result = active_runner.run(code, test_eval_path)
    except Exception as exc:
        sandbox_result = SandboxResult(
            outcome="error",
            tests_total=0,
            tests_passed=0,
            error_category="SandboxError",
            diagnostic_output=f"Falha interna ao executar sandbox: {exc}",
        )

    with transaction(pool) as conn:
        return finalize_attempt(
            conn,
            reserved.attempt.id,
            sandbox_result,
            actor=actor,
        )


def recover_stale_attempts(
    conn: DictConnection,
    *,
    min_age_seconds: int = 0,
    actor: str = "daemon",
) -> list[Attempt]:
    """Mark orphaned 'running' attempts as 'error' and exhaust 3rd-attempt pending assignments."""
    rows = conn.execute(
        "SELECT att.id AS attempt_id, att.assignment_id, att.number, a.state AS assignment_state "
        "FROM attempts att "
        "JOIN assignments a ON a.id = att.assignment_id "
        "WHERE att.status = 'running' "
        "AND att.started_at <= now() - make_interval(secs => %s) "
        "ORDER BY att.id "
        "FOR UPDATE OF att, a",
        (min_age_seconds,),
    ).fetchall()

    if not rows:
        return []

    recovered: list[Attempt] = []
    for r in rows:
        att_id = int(r["attempt_id"])
        aid = int(r["assignment_id"])
        num = int(r["number"])
        a_state = str(r["assignment_state"])

        updated_row = conn.execute(
            "UPDATE attempts "
            "SET status = %s, tests_total = %s, tests_passed = %s, "
            "output = %s, finished_at = now() "
            "WHERE id = %s "
            "RETURNING id, assignment_id, number, status, tests_total, tests_passed, "
            "output, code, started_at, finished_at",
            (
                "error",
                0,
                0,
                "Tentativa interrompida por falha ou reinício do servidor",
                att_id,
            ),
        ).fetchone()
        assert updated_row is not None
        recovered.append(_row_to_attempt(updated_row))

        if num >= _MAX_ATTEMPTS and a_state == "pending":
            conn.execute(
                "UPDATE assignments SET state = %s, points = %s WHERE id = %s",
                ("exhausted", Decimal("0.0"), aid),
            )

    audit_details = {
        "recovered_attempt_ids": [att.id for att in recovered],
        "count": len(recovered),
    }
    conn.execute(
        "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
        (actor, "recover_stale_attempts", json.dumps(audit_details)),
    )

    return recovered
