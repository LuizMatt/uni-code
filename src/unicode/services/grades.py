"""Read-only grade and analytics queries for the professor panel and admin CLI.

All queries in this module only execute SELECT statements on tables/views granted
to the `unicode_panel` role (`students`, `units`, `questions`, `assignments`,
`attempts`, `grades_by_unit`).
"""

import csv
import io
from collections.abc import Sequence
from typing import cast

from unicode.db import DictConnection
from unicode.models.assignment import AssignmentState
from unicode.models.attempt import AttemptStatus
from unicode.models.grade import (
    AssignmentHistoryItem,
    AttemptDetail,
    OverviewStats,
    QuestionRateStat,
    StudentDetailReport,
    StudentGradesSummary,
    StudentUnitGrade,
    UnitDetailReport,
    UnitSummary,
)
from unicode.models.student import Student


class GradeReportError(Exception):
    """Raised when a requested student or unit does not exist."""


def get_overview_stats(conn: DictConnection) -> tuple[OverviewStats, list[UnitSummary]]:
    """Return high-level system counters and per-unit summary metrics."""
    row = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM students) AS total_students,
            (SELECT COUNT(*) FROM units) AS total_units,
            (SELECT COUNT(*) FROM questions WHERE active = TRUE) AS active_questions,
            (
                SELECT COUNT(*) FROM attempts
                WHERE started_at >= date_trunc('day', now())
            ) AS submissions_today,
            (
                SELECT COUNT(*) FROM assignments
                WHERE state = 'passed'
            ) AS approved_assignments,
            (
                SELECT COUNT(*) FROM assignments
                WHERE state IN ('passed', 'exhausted')
            ) AS decided_assignments
        """
    ).fetchone()

    assert row is not None
    total_students = int(row["total_students"])
    total_units = int(row["total_units"])
    active_questions = int(row["active_questions"])
    submissions_today = int(row["submissions_today"])
    approved = int(row["approved_assignments"])
    decided = int(row["decided_assignments"])
    approval_rate = round((approved / decided) * 100.0, 1) if decided > 0 else 0.0

    overview = OverviewStats(
        total_students=total_students,
        total_units=total_units,
        active_questions=active_questions,
        submissions_today=submissions_today,
        approved_assignments=approved,
        decided_assignments=decided,
        approval_rate=approval_rate,
    )

    unit_rows = conn.execute(
        """
        SELECT
            u.code,
            u.title,
            COUNT(DISTINCT q.id) FILTER (WHERE q.active = TRUE) AS active_questions,
            COUNT(DISTINCT g.registration) AS students_started,
            COALESCE(AVG(g.points), 0) AS average_points
        FROM units u
        LEFT JOIN questions q ON q.unit_id = u.id
        LEFT JOIN grades_by_unit g ON g.unit = u.code
        GROUP BY u.id, u.code, u.title
        ORDER BY u.code ASC
        """
    ).fetchall()

    units = [
        UnitSummary(
            code=str(r["code"]),
            title=str(r["title"]),
            active_questions=int(r["active_questions"]),
            students_started=int(r["students_started"]),
            average_points=round(float(r["average_points"]), 2),
        )
        for r in unit_rows
    ]
    return overview, units


def list_student_grades_summary(
    conn: DictConnection,
    *,
    unit_code: str | None = None,
    class_group: str | None = None,
) -> list[StudentGradesSummary]:
    """List students with their points per unit and total points."""
    if class_group is not None:
        student_rows = conn.execute(
            """
            SELECT registration, email, name, class_group
            FROM students
            WHERE class_group = %s
            ORDER BY registration ASC
            """,
            (class_group,),
        ).fetchall()
    else:
        student_rows = conn.execute(
            """
            SELECT registration, email, name, class_group
            FROM students
            ORDER BY registration ASC
            """
        ).fetchall()

    if unit_code is not None:
        grade_rows = conn.execute(
            """
            SELECT registration, unit, points
            FROM grades_by_unit
            WHERE unit = %s
            """,
            (unit_code,),
        ).fetchall()
    else:
        grade_rows = conn.execute(
            """
            SELECT registration, unit, points
            FROM grades_by_unit
            """
        ).fetchall()

    grades_map: dict[str, dict[str, float]] = {}
    for g in grade_rows:
        reg = str(g["registration"])
        unit = str(g["unit"])
        pts = float(g["points"])
        grades_map.setdefault(reg, {})[unit] = pts

    summaries: list[StudentGradesSummary] = []
    for s in student_rows:
        reg = str(s["registration"])
        student_grades = grades_map.get(reg, {})
        total = round(sum(student_grades.values()), 2)
        summaries.append(
            StudentGradesSummary(
                registration=reg,
                email=str(s["email"]),
                name=str(s["name"]) if s["name"] is not None else None,
                class_group=str(s["class_group"]) if s["class_group"] is not None else None,
                grades_by_unit=dict(sorted(student_grades.items())),
                total_points=total,
            )
        )
    return summaries


def list_unit_grades_for_export(
    conn: DictConnection,
    unit_code: str,
    *,
    class_group: str | None = None,
) -> list[StudentUnitGrade]:
    """Return every student's grade in `unit_code` (0.0 for students without assignments)."""
    unit_row = conn.execute(
        "SELECT id, code FROM units WHERE code = %s",
        (unit_code,),
    ).fetchone()
    if unit_row is None:
        raise GradeReportError(f"Unidade '{unit_code}' não encontrada.")

    if class_group is not None:
        rows = conn.execute(
            """
            SELECT
                s.registration,
                s.email,
                s.name,
                s.class_group,
                COALESCE(g.points, 0) AS points
            FROM students s
            LEFT JOIN grades_by_unit g
                ON g.registration = s.registration AND g.unit = %s
            WHERE s.class_group = %s
            ORDER BY s.registration ASC
            """,
            (unit_code, class_group),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT
                s.registration,
                s.email,
                s.name,
                s.class_group,
                COALESCE(g.points, 0) AS points
            FROM students s
            LEFT JOIN grades_by_unit g
                ON g.registration = s.registration AND g.unit = %s
            ORDER BY s.registration ASC
            """,
            (unit_code,),
        ).fetchall()

    return [
        StudentUnitGrade(
            registration=str(r["registration"]),
            email=str(r["email"]),
            name=str(r["name"]) if r["name"] is not None else None,
            class_group=str(r["class_group"]) if r["class_group"] is not None else None,
            unit_code=unit_code,
            points=float(r["points"]),
        )
        for r in rows
    ]


def format_grades_csv(rows: Sequence[StudentUnitGrade]) -> str:
    """Serialize unit grades to a UTF-8 CSV string."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["matricula", "email", "nome", "turma", "unidade", "pontos"])
    for r in rows:
        writer.writerow(
            [
                r.registration,
                r.email,
                r.name or "",
                r.class_group or "",
                r.unit_code,
                f"{r.points:.1f}",
            ]
        )
    return buf.getvalue()


def get_student_detail_report(
    conn: DictConnection,
    registration: str,
) -> StudentDetailReport:
    """Return full assignment and attempt history for a student."""
    student_row = conn.execute(
        """
        SELECT registration, email, name, class_group, created_at
        FROM students
        WHERE registration = %s
        """,
        (registration,),
    ).fetchone()
    if student_row is None:
        raise GradeReportError(f"Aluno '{registration}' não encontrado.")

    student = Student(
        registration=str(student_row["registration"]),
        email=str(student_row["email"]),
        name=str(student_row["name"]) if student_row["name"] is not None else None,
        class_group=(
            str(student_row["class_group"])
            if student_row["class_group"] is not None
            else None
        ),
        created_at=student_row["created_at"],
    )

    grade_rows = conn.execute(
        """
        SELECT unit, points
        FROM grades_by_unit
        WHERE registration = %s
        ORDER BY unit ASC
        """,
        (registration,),
    ).fetchall()
    grades_by_unit = {str(r["unit"]): float(r["points"]) for r in grade_rows}
    total_points = round(sum(grades_by_unit.values()), 2)

    assignment_rows = conn.execute(
        """
        SELECT
            a.id,
            u.code AS unit_code,
            q.slug AS question_slug,
            q.title AS question_title,
            a.round,
            a.state,
            a.points,
            a.created_at
        FROM assignments a
        JOIN units u ON u.id = a.unit_id
        JOIN questions q ON q.id = a.question_id
        WHERE a.student_registration = %s
        ORDER BY u.code ASC, a.round DESC, q.slug ASC, a.id ASC
        """,
        (registration,),
    ).fetchall()

    attempt_rows = conn.execute(
        """
        SELECT
            att.id,
            att.assignment_id,
            att.number,
            att.status,
            att.tests_total,
            att.tests_passed,
            att.output,
            att.code,
            att.started_at,
            att.finished_at
        FROM attempts att
        JOIN assignments a ON a.id = att.assignment_id
        WHERE a.student_registration = %s
        ORDER BY att.assignment_id ASC, att.number ASC
        """,
        (registration,),
    ).fetchall()

    attempts_by_assignment: dict[int, list[AttemptDetail]] = {}
    for att in attempt_rows:
        assignment_id = int(att["assignment_id"])
        attempts_by_assignment.setdefault(assignment_id, []).append(
            AttemptDetail(
                id=int(att["id"]),
                number=int(att["number"]),
                status=cast(AttemptStatus, str(att["status"])),
                tests_total=(
                    int(att["tests_total"]) if att["tests_total"] is not None else None
                ),
                tests_passed=(
                    int(att["tests_passed"]) if att["tests_passed"] is not None else None
                ),
                output=str(att["output"]) if att["output"] is not None else None,
                code=str(att["code"]),
                started_at=att["started_at"],
                finished_at=att["finished_at"],
            )
        )

    assignments = tuple(
        AssignmentHistoryItem(
            id=int(a["id"]),
            unit_code=str(a["unit_code"]),
            question_slug=str(a["question_slug"]),
            question_title=str(a["question_title"]),
            round=int(a["round"]),
            state=cast(AssignmentState, str(a["state"])),
            points=float(a["points"]),
            created_at=a["created_at"],
            attempts=tuple(attempts_by_assignment.get(int(a["id"]), [])),
        )
        for a in assignment_rows
    )

    return StudentDetailReport(
        student=student,
        grades_by_unit=grades_by_unit,
        total_points=total_points,
        assignments=assignments,
    )


def get_unit_detail_report(conn: DictConnection, unit_code: str) -> UnitDetailReport:
    """Return hit-rate and attempt statistics for every question in a unit."""
    unit_row = conn.execute(
        "SELECT id, code, title FROM units WHERE code = %s",
        (unit_code,),
    ).fetchone()
    if unit_row is None:
        raise GradeReportError(f"Unidade '{unit_code}' não encontrada.")

    question_rows = conn.execute(
        """
        SELECT
            q.slug,
            q.title,
            q.active,
            COUNT(a.id) FILTER (WHERE a.state <> 'replaced') AS assigned_count,
            COUNT(a.id) FILTER (WHERE a.state = 'passed') AS passed_count,
            COUNT(a.id) FILTER (WHERE a.state = 'exhausted') AS exhausted_count,
            COUNT(a.id) FILTER (WHERE a.state = 'pending') AS pending_count,
            COALESCE(
                AVG(att_counts.cnt) FILTER (WHERE a.state <> 'replaced'),
                0
            ) AS avg_attempts
        FROM questions q
        LEFT JOIN assignments a ON a.question_id = q.id
        LEFT JOIN (
            SELECT assignment_id, COUNT(*) AS cnt
            FROM attempts
            GROUP BY assignment_id
        ) att_counts ON att_counts.assignment_id = a.id
        WHERE q.unit_id = %s
        GROUP BY q.id, q.slug, q.title, q.active
        ORDER BY q.slug ASC
        """,
        (unit_row["id"],),
    ).fetchall()

    questions: list[QuestionRateStat] = []
    for q in question_rows:
        assigned = int(q["assigned_count"])
        passed = int(q["passed_count"])
        exhausted = int(q["exhausted_count"])
        pending = int(q["pending_count"])
        pass_rate = round((passed / assigned) * 100.0, 1) if assigned > 0 else 0.0
        questions.append(
            QuestionRateStat(
                slug=str(q["slug"]),
                title=str(q["title"]),
                active=bool(q["active"]),
                assigned_count=assigned,
                passed_count=passed,
                exhausted_count=exhausted,
                pending_count=pending,
                pass_rate=pass_rate,
                avg_attempts=round(float(q["avg_attempts"]), 2),
            )
        )

    return UnitDetailReport(
        code=str(unit_row["code"]),
        title=str(unit_row["title"]),
        questions=tuple(questions),
    )
