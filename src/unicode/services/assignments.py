import json
import secrets
import shutil
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from unicode.db import DictConnection
from unicode.models.assignment import (
    Assignment,
    AssignmentState,
    DrawResult,
    QuestionStatus,
    ResetResult,
)

_QUESTIONS_PER_UNIT = 2
_MAX_ATTEMPTS_PER_ASSIGNMENT = 3
_rng = secrets.SystemRandom()


class AssignmentError(Exception):
    """Base exception for assignment draw and reset errors."""


class StudentNotFoundError(AssignmentError):
    """Raised when the student registration does not exist."""


class UnitNotFoundError(AssignmentError):
    """Raised when the unit code does not exist."""


class InsufficientQuestionsError(AssignmentError):
    """Raised when a unit has fewer active questions than needed for a draw."""


class NoActiveAssignmentsError(AssignmentError):
    """Raised when attempting to reset a student with no active assignments."""


def _get_student_and_unit(
    conn: DictConnection, registration: str, unit_code: str
) -> int:
    student_row = conn.execute(
        "SELECT registration FROM students WHERE registration = %s",
        (registration,),
    ).fetchone()
    if student_row is None:
        raise StudentNotFoundError(f"aluno '{registration}' não encontrado")

    unit_row = conn.execute(
        "SELECT id, code FROM units WHERE code = %s",
        (unit_code,),
    ).fetchone()
    if unit_row is None:
        raise UnitNotFoundError(f"unidade '{unit_code}' não encontrada")

    return int(unit_row["id"])


def _acquire_student_unit_lock(
    conn: DictConnection, registration: str, unit_id: int
) -> None:
    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtext(%s), %s)",
        (registration, unit_id),
    )


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


def _fetch_active_assignments(
    conn: DictConnection, registration: str, unit_id: int
) -> list[Assignment]:
    rows = conn.execute(
        "SELECT a.id, a.student_registration, a.unit_id, u.code AS unit_code, "
        "a.question_id, q.slug AS question_slug, a.round, a.state, a.points, a.created_at "
        "FROM assignments a "
        "JOIN questions q ON q.id = a.question_id "
        "JOIN units u ON u.id = a.unit_id "
        "WHERE a.student_registration = %s AND a.unit_id = %s AND a.state <> 'replaced' "
        "ORDER BY a.id",
        (registration, unit_id),
    ).fetchall()
    return [_row_to_assignment(r) for r in rows]


def list_active_assignments(
    conn: DictConnection, registration: str, unit_code: str
) -> list[Assignment]:
    """Return active (non-replaced) assignments for a student in a unit."""
    unit_id = _get_student_and_unit(conn, registration, unit_code)
    return _fetch_active_assignments(conn, registration, unit_id)


def _insert_assignments(
    conn: DictConnection,
    registration: str,
    unit_id: int,
    unit_code: str,
    questions: list[dict[str, Any]],
    round_num: int,
) -> list[Assignment]:
    created: list[Assignment] = []
    for q in sorted(questions, key=lambda item: int(item["id"])):
        q_id = int(q["id"])
        q_slug = str(q["slug"])
        row = conn.execute(
            "INSERT INTO assignments "
            "(student_registration, question_id, unit_id, round, state, points) "
            "VALUES (%s, %s, %s, %s, 'pending', 0) "
            "RETURNING id, state, points, created_at",
            (registration, q_id, unit_id, round_num),
        ).fetchone()
        assert row is not None
        created.append(
            Assignment(
                id=int(row["id"]),
                student_registration=registration,
                unit_id=unit_id,
                unit_code=unit_code,
                question_id=q_id,
                question_slug=q_slug,
                round=round_num,
                state=cast(AssignmentState, str(row["state"])),
                points=Decimal(str(row["points"])),
                created_at=cast(datetime, row["created_at"]),
            )
        )
    return created


def draw_assignments(
    conn: DictConnection,
    registration: str,
    unit_code: str,
    *,
    actor: str | None = None,
) -> DrawResult:
    """Draw 2 active questions for a student in a unit, or return existing ones idempotently."""
    unit_id = _get_student_and_unit(conn, registration, unit_code)
    _acquire_student_unit_lock(conn, registration, unit_id)

    existing = _fetch_active_assignments(conn, registration, unit_id)
    if existing:
        return DrawResult(
            student_registration=registration,
            unit_code=unit_code,
            assignments=existing,
            created=False,
        )

    active_questions = conn.execute(
        "SELECT id, slug FROM questions WHERE unit_id = %s AND active = TRUE ORDER BY id",
        (unit_id,),
    ).fetchall()

    if len(active_questions) < _QUESTIONS_PER_UNIT:
        raise InsufficientQuestionsError(
            f"unidade '{unit_code}' possui apenas {len(active_questions)} questão(ões) ativa(s); "
            f"mínimo necessário: {_QUESTIONS_PER_UNIT}"
        )

    picked = _rng.sample(active_questions, _QUESTIONS_PER_UNIT)
    new_assignments = _insert_assignments(
        conn,
        registration,
        unit_id,
        unit_code,
        picked,
        round_num=1,
    )

    audit_details = {
        "student_registration": registration,
        "unit_code": unit_code,
        "round": 1,
        "questions": [a.question_slug for a in new_assignments],
    }
    conn.execute(
        "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
        (actor or registration, "draw_assignments", json.dumps(audit_details)),
    )

    return DrawResult(
        student_registration=registration,
        unit_code=unit_code,
        assignments=new_assignments,
        created=True,
    )


def reset_assignments(
    conn: DictConnection,
    registration: str,
    unit_code: str,
    *,
    question_slug: str | None = None,
    actor: str = "admin",
) -> ResetResult:
    """Replace active assignments (all in unit or a single question) and draw new ones."""
    unit_id = _get_student_and_unit(conn, registration, unit_code)
    _acquire_student_unit_lock(conn, registration, unit_id)

    active_assignments = _fetch_active_assignments(conn, registration, unit_id)
    if not active_assignments:
        raise NoActiveAssignmentsError(
            f"aluno '{registration}' não possui sorteio ativo na unidade '{unit_code}'"
        )

    if question_slug is not None:
        targets = [a for a in active_assignments if a.question_slug == question_slug]
        if not targets:
            raise NoActiveAssignmentsError(
                f"questão '{question_slug}' não faz parte do sorteio ativo "
                f"do aluno '{registration}' na unidade '{unit_code}'"
            )
        kept_ids = {a.question_id for a in active_assignments if a.question_slug != question_slug}
    else:
        targets = list(active_assignments)
        kept_ids = set()

    needed_count = len(targets)
    just_replaced_ids = {a.question_id for a in targets}

    history_rows = conn.execute(
        "SELECT question_id, round FROM assignments "
        "WHERE student_registration = %s AND unit_id = %s",
        (registration, unit_id),
    ).fetchall()
    ever_drawn_ids = {int(r["question_id"]) for r in history_rows}
    max_round = max((int(r["round"]) for r in history_rows), default=1)
    new_round = max_round + 1

    active_questions = conn.execute(
        "SELECT id, slug FROM questions WHERE unit_id = %s AND active = TRUE ORDER BY id",
        (unit_id,),
    ).fetchall()

    available_questions = [
        q for q in active_questions if int(q["id"]) not in kept_ids
    ]
    if len(available_questions) < needed_count:
        raise InsufficientQuestionsError(
            f"unidade '{unit_code}' não possui questões ativas suficientes para o reset "
            f"(disponíveis: {len(available_questions)}, necessárias: {needed_count})"
        )

    # Tier 1: active questions never drawn for this student in this unit
    tier1 = [q for q in available_questions if int(q["id"]) not in ever_drawn_ids]
    # Tier 2: active questions drawn in older rounds (excluding the ones being replaced now)
    tier2 = [
        q
        for q in available_questions
        if int(q["id"]) in ever_drawn_ids and int(q["id"]) not in just_replaced_ids
    ]
    # Tier 3: the questions being replaced right now (last resort)
    tier3 = [q for q in available_questions if int(q["id"]) in just_replaced_ids]

    picked: list[dict[str, Any]] = []
    reused_questions = False

    if len(tier1) >= needed_count:
        picked.extend(_rng.sample(tier1, needed_count))
    else:
        picked.extend(tier1)
        reused_questions = True
        remaining = needed_count - len(picked)
        if len(tier2) >= remaining:
            picked.extend(_rng.sample(tier2, remaining))
        else:
            picked.extend(tier2)
            remaining = needed_count - len(picked)
            picked.extend(_rng.sample(tier3, remaining))

    target_ids = [a.id for a in targets]
    conn.execute(
        "UPDATE assignments SET state = 'replaced', points = 0 WHERE id = ANY(%s)",
        (target_ids,),
    )

    new_assignments = _insert_assignments(
        conn,
        registration,
        unit_id,
        unit_code,
        picked,
        round_num=new_round,
    )

    audit_details = {
        "student_registration": registration,
        "unit_code": unit_code,
        "question_slug": question_slug,
        "new_round": new_round,
        "replaced_questions": [a.question_slug for a in targets],
        "new_questions": [a.question_slug for a in new_assignments],
        "reused_questions": reused_questions,
    }
    conn.execute(
        "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
        (actor, "reset_assignments", json.dumps(audit_details)),
    )

    return ResetResult(
        student_registration=registration,
        unit_code=unit_code,
        new_round=new_round,
        replaced_assignments=targets,
        new_assignments=new_assignments,
        reused_questions=reused_questions,
    )


def provision_workspace(
    workspaces_dir: Path,
    questions_dir: Path,
    assignments: Sequence[Assignment],
) -> list[Path]:
    """Create student workspace folders with README.md and initial solution.py."""
    provisioned: list[Path] = []
    for a in assignments:
        src_dir = questions_dir / a.unit_code / a.question_slug
        readme_src = src_dir / "README.md"
        template_src = src_dir / "template.py"
        if not readme_src.exists() or not template_src.exists():
            continue

        dest_dir = workspaces_dir / a.student_registration / a.unit_code / a.question_slug
        dest_dir.mkdir(parents=True, exist_ok=True)

        shutil.copyfile(readme_src, dest_dir / "README.md")

        solution_dest = dest_dir / "solution.py"
        if not solution_dest.exists():
            shutil.copyfile(template_src, solution_dest)

        provisioned.append(dest_dir)

    return provisioned


def archive_replaced_workspaces(
    workspaces_dir: Path,
    replaced_assignments: Sequence[Assignment],
) -> list[Path]:
    """Move replaced question workspaces to _archive/round-<N>/<slug>/."""
    archived: list[Path] = []
    for a in replaced_assignments:
        unit_ws = workspaces_dir / a.student_registration / a.unit_code
        current_dir = unit_ws / a.question_slug
        if not current_dir.exists():
            continue

        archive_dir = unit_ws / "_archive" / f"round-{a.round}" / a.question_slug
        if archive_dir.exists():
            shutil.rmtree(archive_dir)
        archive_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(current_dir), str(archive_dir))
        archived.append(archive_dir)

    return archived


def get_student_status(
    conn: DictConnection,
    registration: str,
    *,
    unit_code: str | None = None,
) -> list[QuestionStatus]:
    """Return active assignment status (including attempt counts) for a student."""
    student_row = conn.execute(
        "SELECT registration FROM students WHERE registration = %s",
        (registration,),
    ).fetchone()
    if student_row is None:
        raise StudentNotFoundError(f"aluno '{registration}' não encontrado")

    if unit_code is not None:
        unit_row = conn.execute(
            "SELECT id FROM units WHERE code = %s",
            (unit_code,),
        ).fetchone()
        if unit_row is None:
            raise UnitNotFoundError(f"unidade '{unit_code}' não encontrada")
        rows = conn.execute(
            "SELECT u.code AS unit_code, q.slug AS question_slug, q.title AS question_title, "
            "a.round, a.state, a.points, COUNT(att.id) AS attempts_used "
            "FROM assignments a "
            "JOIN units u ON u.id = a.unit_id "
            "JOIN questions q ON q.id = a.question_id "
            "LEFT JOIN attempts att ON att.assignment_id = a.id "
            "WHERE a.student_registration = %s AND u.code = %s AND a.state <> 'replaced' "
            "GROUP BY a.id, u.code, q.slug, q.title, a.round, a.state, a.points "
            "ORDER BY u.code, a.id",
            (registration, unit_code),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT u.code AS unit_code, q.slug AS question_slug, q.title AS question_title, "
            "a.round, a.state, a.points, COUNT(att.id) AS attempts_used "
            "FROM assignments a "
            "JOIN units u ON u.id = a.unit_id "
            "JOIN questions q ON q.id = a.question_id "
            "LEFT JOIN attempts att ON att.assignment_id = a.id "
            "WHERE a.student_registration = %s AND a.state <> 'replaced' "
            "GROUP BY a.id, u.code, q.slug, q.title, a.round, a.state, a.points "
            "ORDER BY u.code, a.id",
            (registration,),
        ).fetchall()

    result: list[QuestionStatus] = []
    for r in rows:
        state = cast(AssignmentState, str(r["state"]))
        used = int(r["attempts_used"])
        remaining = (
            0
            if state in ("passed", "exhausted", "replaced")
            else max(0, _MAX_ATTEMPTS_PER_ASSIGNMENT - used)
        )
        result.append(
            QuestionStatus(
                unit_code=str(r["unit_code"]),
                question_slug=str(r["question_slug"]),
                question_title=str(r["question_title"]),
                round=int(r["round"]),
                state=state,
                points=Decimal(str(r["points"])),
                attempts_used=used,
                attempts_remaining=remaining,
            )
        )
    return result


def resolve_student_question_unit(
    conn: DictConnection,
    registration: str,
    question_slug: str,
) -> str:
    """Resolve the active unit_code for a student's drawn question_slug."""
    row = conn.execute(
        "SELECT u.code AS unit_code "
        "FROM assignments a "
        "JOIN units u ON u.id = a.unit_id "
        "JOIN questions q ON q.id = a.question_id "
        "WHERE a.student_registration = %s AND q.slug = %s AND a.state <> 'replaced'",
        (registration, question_slug),
    ).fetchone()
    if row is None:
        raise NoActiveAssignmentsError(
            f"questão '{question_slug}' não faz parte de nenhum sorteio ativo "
            f"do aluno '{registration}'"
        )
    return str(row["unit_code"])
