from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from unicode.models.grade import StudentUnitGrade
from unicode.services.grades import (
    GradeReportError,
    format_grades_csv,
    get_overview_stats,
    get_student_detail_report,
    get_unit_detail_report,
    list_student_grades_summary,
    list_unit_grades_for_export,
)


class FakeGradeCursor:
    def __init__(
        self,
        *,
        one: dict[str, Any] | None = None,
        many: list[dict[str, Any]] | None = None,
    ) -> None:
        self._one = one
        self._many = many or []

    def fetchone(self) -> dict[str, Any] | None:
        return self._one

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._many)


class FakeGradeConn:
    def __init__(self, responses: list[FakeGradeCursor]) -> None:
        self._responses = list(responses)
        self.queries: list[tuple[str, Any]] = []

    def execute(self, query: str, params: Any = None) -> FakeGradeCursor:
        self.queries.append((query, params))
        if not self._responses:
            raise AssertionError(f"Unexpected query: {query}")
        return self._responses.pop(0)


def test_get_overview_stats_calculates_approval_rate() -> None:
    conn = FakeGradeConn(
        [
            FakeGradeCursor(
                one={
                    "total_students": 25,
                    "total_units": 2,
                    "active_questions": 10,
                    "submissions_today": 14,
                    "approved_assignments": 15,
                    "decided_assignments": 20,
                }
            ),
            FakeGradeCursor(
                many=[
                    {
                        "code": "unit-01",
                        "title": "Unidade 1",
                        "active_questions": 5,
                        "students_started": 12,
                        "average_points": Decimal("0.75"),
                    }
                ]
            ),
        ]
    )
    overview, units = get_overview_stats(conn)  # type: ignore[arg-type]
    assert overview.total_students == 25
    assert overview.submissions_today == 14
    assert overview.approval_rate == 75.0
    assert len(units) == 1
    assert units[0].code == "unit-01"
    assert units[0].average_points == 0.75


def test_list_student_grades_summary_aggregates_by_student() -> None:
    conn = FakeGradeConn(
        [
            FakeGradeCursor(
                many=[
                    {
                        "registration": "20240001",
                        "email": "ana@edu.br",
                        "name": "Ana",
                        "class_group": "T01",
                    },
                    {
                        "registration": "20240002",
                        "email": "bruno@edu.br",
                        "name": "Bruno",
                        "class_group": "T01",
                    },
                ]
            ),
            FakeGradeCursor(
                many=[
                    {
                        "registration": "20240001",
                        "unit": "unit-01",
                        "points": Decimal("1.0"),
                    },
                    {
                        "registration": "20240001",
                        "unit": "unit-02",
                        "points": Decimal("0.5"),
                    },
                ]
            ),
        ]
    )
    summaries = list_student_grades_summary(conn)  # type: ignore[arg-type]
    assert len(summaries) == 2
    assert summaries[0].registration == "20240001"
    assert summaries[0].grades_by_unit == {"unit-01": 1.0, "unit-02": 0.5}
    assert summaries[0].total_points == 1.5
    assert summaries[1].registration == "20240002"
    assert summaries[1].grades_by_unit == {}
    assert summaries[1].total_points == 0.0


def test_list_student_grades_summary_filters_by_unit_and_class_group() -> None:
    conn = FakeGradeConn(
        [
            FakeGradeCursor(
                many=[
                    {
                        "registration": "20240001",
                        "email": "ana@edu.br",
                        "name": "Ana",
                        "class_group": "T01",
                    },
                ]
            ),
            FakeGradeCursor(
                many=[
                    {
                        "registration": "20240001",
                        "unit": "unit-01",
                        "points": Decimal("1.0"),
                    },
                ]
            ),
        ]
    )
    summaries = list_student_grades_summary(
        conn,  # type: ignore[arg-type]
        unit_code="unit-01",
        class_group="T01",
    )
    assert len(summaries) == 1
    assert summaries[0].registration == "20240001"
    assert summaries[0].grades_by_unit == {"unit-01": 1.0}
    assert summaries[0].total_points == 1.0
    assert conn.queries[0][1] == ("T01",)
    assert conn.queries[1][1] == ("unit-01",)


def test_list_unit_grades_for_export_returns_rows_with_and_without_class_group() -> None:
    conn = FakeGradeConn(
        [
            FakeGradeCursor(one={"id": 1, "code": "unit-01"}),
            FakeGradeCursor(
                many=[
                    {
                        "registration": "20240001",
                        "email": "ana@edu.br",
                        "name": "Ana",
                        "class_group": "T01",
                        "points": Decimal("1.0"),
                    },
                    {
                        "registration": "20240002",
                        "email": "bob@edu.br",
                        "name": None,
                        "class_group": None,
                        "points": Decimal("0"),
                    },
                ]
            ),
            FakeGradeCursor(one={"id": 1, "code": "unit-01"}),
            FakeGradeCursor(
                many=[
                    {
                        "registration": "20240001",
                        "email": "ana@edu.br",
                        "name": "Ana",
                        "class_group": "T01",
                        "points": Decimal("1.0"),
                    },
                ]
            ),
        ]
    )
    all_rows = list_unit_grades_for_export(conn, "unit-01")  # type: ignore[arg-type]
    assert len(all_rows) == 2
    assert all_rows[0].points == 1.0
    assert all_rows[1].points == 0.0
    assert all_rows[1].name is None
    assert conn.queries[1][1] == ("unit-01",)

    filtered_rows = list_unit_grades_for_export(
        conn,  # type: ignore[arg-type]
        "unit-01",
        class_group="T01",
    )
    assert len(filtered_rows) == 1
    assert filtered_rows[0].class_group == "T01"
    assert conn.queries[3][1] == ("unit-01", "T01")


def test_list_unit_grades_for_export_raises_when_unit_missing() -> None:
    conn = FakeGradeConn([FakeGradeCursor(one=None)])
    with pytest.raises(GradeReportError, match="Unidade 'unit-99' não encontrada"):
        list_unit_grades_for_export(conn, "unit-99")  # type: ignore[arg-type]


def test_format_grades_csv_generates_expected_columns() -> None:
    rows = [
        StudentUnitGrade(
            registration="00123",
            email="ana@edu.br",
            name="Ana Silva",
            class_group="T01",
            unit_code="unit-01",
            points=1.0,
        ),
        StudentUnitGrade(
            registration="00124",
            email="bob@edu.br",
            name=None,
            class_group=None,
            unit_code="unit-01",
            points=0.0,
        ),
    ]
    csv_text = format_grades_csv(rows)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "matricula,email,nome,turma,unidade,pontos"
    assert lines[1] == "00123,ana@edu.br,Ana Silva,T01,unit-01,1.0"
    assert lines[2] == "00124,bob@edu.br,,,unit-01,0.0"


def test_get_student_detail_report_includes_assignments_and_attempts() -> None:
    now = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    conn = FakeGradeConn(
        [
            FakeGradeCursor(
                one={
                    "registration": "20240001",
                    "email": "ana@edu.br",
                    "name": "Ana",
                    "class_group": "T01",
                    "created_at": now,
                }
            ),
            FakeGradeCursor(
                many=[
                    {
                        "unit": "unit-01",
                        "points": Decimal("0.5"),
                    }
                ]
            ),
            FakeGradeCursor(
                many=[
                    {
                        "id": 10,
                        "unit_code": "unit-01",
                        "question_slug": "soma-dois-numeros",
                        "question_title": "Soma de Dois Números",
                        "round": 1,
                        "state": "passed",
                        "points": Decimal("0.5"),
                        "created_at": now,
                    }
                ]
            ),
            FakeGradeCursor(
                many=[
                    {
                        "id": 100,
                        "assignment_id": 10,
                        "number": 1,
                        "status": "passed",
                        "tests_total": 4,
                        "tests_passed": 4,
                        "output": "4/4 testes passaram",
                        "code": "def soma(a, b):\n    return a + b\n",
                        "started_at": now,
                        "finished_at": now,
                    }
                ]
            ),
        ]
    )
    report = get_student_detail_report(conn, "20240001")  # type: ignore[arg-type]
    assert report.student.registration == "20240001"
    assert report.total_points == 0.5
    assert len(report.assignments) == 1
    assert report.assignments[0].question_slug == "soma-dois-numeros"
    assert len(report.assignments[0].attempts) == 1
    assert "return a + b" in report.assignments[0].attempts[0].code


def test_get_student_detail_report_raises_when_student_missing() -> None:
    conn = FakeGradeConn([FakeGradeCursor(one=None)])
    with pytest.raises(GradeReportError, match="Aluno '99999999' não encontrado"):
        get_student_detail_report(conn, "99999999")  # type: ignore[arg-type]


def test_get_unit_detail_report_computes_question_rates() -> None:
    conn = FakeGradeConn(
        [
            FakeGradeCursor(one={"id": 1, "code": "unit-01", "title": "Unidade 1"}),
            FakeGradeCursor(
                many=[
                    {
                        "slug": "fatorial",
                        "title": "Fatorial",
                        "active": True,
                        "assigned_count": 4,
                        "passed_count": 3,
                        "exhausted_count": 1,
                        "pending_count": 0,
                        "avg_attempts": Decimal("1.75"),
                    }
                ]
            ),
        ]
    )
    report = get_unit_detail_report(conn, "unit-01")  # type: ignore[arg-type]
    assert report.code == "unit-01"
    assert len(report.questions) == 1
    q = report.questions[0]
    assert q.pass_rate == 75.0
    assert q.avg_attempts == 1.75


def test_get_unit_detail_report_raises_when_unit_missing() -> None:
    conn = FakeGradeConn([FakeGradeCursor(one=None)])
    with pytest.raises(GradeReportError, match="Unidade 'unit-99' não encontrada"):
        get_unit_detail_report(conn, "unit-99")  # type: ignore[arg-type]
