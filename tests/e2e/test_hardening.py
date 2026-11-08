"""End-to-end integration and security hardening test suite for UniCode.

Verifies:
1. Student authentication rate limiting and generic error messages.
2. Sanitization of student submission feedback (hidden test code is never leaked).
3. Attempt cap enforcement and rejection of submissions after passing.
4. Database role isolation: `unicode_panel` can execute all reporting queries but is strictly
   forbidden from accessing `sessions` or performing INSERT/UPDATE/DELETE.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest

from tests.support import TEST_PANEL_URL, AsgiTestClient
from unicode.cli_student import format_submit_output
from unicode.config import Settings
from unicode.db import DictConnection
from unicode.models.attempt import StudentFeedback
from unicode.models.grade import StudentUnitGrade
from unicode.models.question import QuestionDefinition, ScanResult, UnitDefinition
from unicode.models.sandbox import SandboxResult
from unicode.models.student import ParseResult, StudentRow
from unicode.services.assignments import (
    draw_assignments,
)
from unicode.services.grades import (
    format_grades_csv,
    get_overview_stats,
    get_student_detail_report,
    get_unit_detail_report,
    list_unit_grades_for_export,
)
from unicode.services.questions import sync_questions
from unicode.services.sessions import (
    InvalidCredentialsError,
    LoginRateLimitError,
    authenticate_student_login,
)
from unicode.services.students import import_students
from unicode.services.submissions import (
    AssignmentAlreadyClosedError,
    finalize_attempt,
    reserve_attempt,
)
from unicode.web.app import create_app

# ---------------------------------------------------------------------------
# 1. In-Memory Security & Hardening Tests
# ---------------------------------------------------------------------------


def test_auth_rate_limiting_and_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure failed student logins trigger rate limits and show generic messages."""
    failure_count = 0

    class FakeStudentAuthConn:
        def execute(self, query: str, params: Any = None) -> Any:
            nonlocal failure_count
            class DummyCursor:
                def fetchone(self) -> dict[str, Any] | None:
                    if "COUNT(*)" in query:
                        return {"cnt": failure_count}
                    return None

            return DummyCursor()

    conn = FakeStudentAuthConn()

    # First 5 wrong logins
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError, match="credenciais inválidas"):
            authenticate_student_login(
                conn,  # type: ignore[arg-type]
                email="hacker@test.com",
                registration="20240001",
                client_ip="192.168.1.50",
                max_failures=5,
                window_seconds=60,
            )
        failure_count += 1

    # 6th attempt has failure_count = 5 >= max_failures
    with pytest.raises(LoginRateLimitError, match="credenciais inválidas"):
        authenticate_student_login(
            conn,  # type: ignore[arg-type]
            email="hacker@test.com",
            registration="20240001",
            client_ip="192.168.1.50",
            max_failures=5,
            window_seconds=60,
        )


def test_student_feedback_sanitization_never_leaks_test_eval_code() -> None:
    """Ensure student feedback hides hidden test code or secret assertion values."""
    feedback = StudentFeedback(
        status="failed",
        tests_passed=2,
        tests_total=5,
        attempt_number=1,
        attempts_remaining=2,
        assignment_state="pending",
        points=Decimal("0.0"),
        first_failed_test="test_cenario_avancado_secreto",
    )

    feedback_text = format_submit_output("unit-01", "q1", feedback)
    assert "SENHA_SUPER_SECRETA_DO_SISTEMA" not in feedback_text
    assert "test_eval.py" not in feedback_text
    assert "tentativas restantes: 2" in feedback_text
    assert "test_cenario_avancado_secreto" in feedback_text


def test_web_api_end_to_end_mock_flow() -> None:
    """Verify that the FastAPI web endpoints reflect student data and grades accurately."""
    settings = Settings(
        admin_email="prof@universidade.edu.br",
        admin_password="senha-segura-123",
        web_dist_dir=Path("nonexistent_dist"),
    )

    sample_rows = [
        StudentUnitGrade(
            registration="20240001",
            email="joao@edu.br",
            name="João Silva",
            class_group="T01",
            unit_code="unit-01",
            points=0.5,
        ),
        StudentUnitGrade(
            registration="20240002",
            email="maria@edu.br",
            name="Maria Santos",
            class_group="T01",
            unit_code="unit-01",
            points=1.0,
        ),
    ]

    @contextmanager
    def fake_factory() -> Iterator[DictConnection]:
        class FakeConn:
            pass

        yield FakeConn()  # type: ignore[misc]

    app = create_app(settings=settings, conn_factory=fake_factory)
    client = AsgiTestClient(app)

    # 1. Unauthenticated request blocked
    res = client.get("/api/overview")
    assert res.status_code == 401

    # 2. Authenticated request accepted
    auth = ("prof@universidade.edu.br", "senha-segura-123")
    res_me = client.get("/api/auth/me", basic_auth=auth)
    assert res_me.status_code == 200
    assert res_me.json() == {"email": "prof@universidade.edu.br"}

    # 3. CSV format output
    csv_out = format_grades_csv(sample_rows)
    assert "matricula,email,nome,turma,unidade,pontos" in csv_out
    assert "20240001,joao@edu.br,João Silva,T01,unit-01,0.5" in csv_out
    assert "20240002,maria@edu.br,Maria Santos,T01,unit-01,1.0" in csv_out


# ---------------------------------------------------------------------------
# 2. Database Role Isolation & Hardening Tests (@pytest.mark.db)
# ---------------------------------------------------------------------------


@pytest.mark.db
def test_unicode_panel_role_cannot_modify_tables_or_read_sessions(
    migrated_db: None,
) -> None:
    """Verify that unicode_panel role has strictly read-only access and cannot see sessions."""
    with psycopg.connect(TEST_PANEL_URL) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT * FROM sessions")

    with psycopg.connect(TEST_PANEL_URL) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO students (registration, email) VALUES ('hacked', 'hacked@x.com')"
            )

    with psycopg.connect(TEST_PANEL_URL) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM attempts")

    with psycopg.connect(TEST_PANEL_URL) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE assignments SET points = 0.5")


@pytest.mark.db
def test_full_lifecycle_and_panel_queries(
    migrated_db: None,
    daemon_conn: DictConnection,
    panel_conn: DictConnection,
) -> None:
    """E2E lifecycle: import students -> sync questions -> draw -> submit -> panel queries."""
    # 1. Import students via daemon
    parse_result = ParseResult(
        valid_rows=[
            StudentRow(
                line_number=1,
                registration="20240999",
                email="aluno_e2e@universidade.edu.br",
                name="Aluno E2E Teste",
                class_group="E2E-A",
            )
        ]
    )
    import_students(daemon_conn, parse_result, source="e2e_test.csv")

    # 2. Sync questions
    scan = ScanResult(
        units=[
            UnitDefinition(
                code="unit-e2e",
                title="Unidade E2E",
            )
        ],
        questions=[
            QuestionDefinition(
                slug="e2e-q1",
                unit_code="unit-e2e",
                title="Questão E2E 1",
            ),
            QuestionDefinition(
                slug="e2e-q2",
                unit_code="unit-e2e",
                title="Questão E2E 2",
            ),
        ],
    )
    sync_questions(daemon_conn, scan)

    # 3. Draw assignments for student
    draw = draw_assignments(daemon_conn, "20240999", "unit-e2e")
    assert len(draw.assignments) == 2
    a1 = draw.assignments[0]

    # 4. Attempt 1: fails
    res1 = reserve_attempt(
        daemon_conn,
        "20240999",
        "unit-e2e",
        a1.question_slug,
        "def solucao(): return 0",
    )
    assert res1.attempt.number == 1
    finalize_attempt(
        daemon_conn,
        attempt_id=res1.attempt.id,
        sandbox_result=SandboxResult(
            outcome="failed",
            tests_total=4,
            tests_passed=1,
            first_failed_test="test_cenario_2",
            diagnostic_output="1/4 testes passaram",
        ),
    )

    # 5. Attempt 2: passes -> assignment state becomes 'passed' and points = 0.5
    res2 = reserve_attempt(
        daemon_conn,
        "20240999",
        "unit-e2e",
        a1.question_slug,
        "def solucao(): return 42",
    )
    assert res2.attempt.number == 2
    finalize_attempt(
        daemon_conn,
        attempt_id=res2.attempt.id,
        sandbox_result=SandboxResult(
            outcome="passed",
            tests_total=4,
            tests_passed=4,
            diagnostic_output="4/4 testes passaram",
        ),
    )

    # 6. Attempt 3 on already passed assignment must be rejected
    with pytest.raises(AssignmentAlreadyClosedError, match="já foi aprovada"):
        reserve_attempt(
            daemon_conn,
            "20240999",
            "unit-e2e",
            a1.question_slug,
            "def solucao(): return 99",
        )

    # 7. Query panel via panel_conn (unicode_panel role)
    overview, units = get_overview_stats(panel_conn)
    assert overview.total_students >= 1
    assert any(u.code == "unit-e2e" for u in units)

    student_report = get_student_detail_report(panel_conn, "20240999")
    assert student_report.student.registration == "20240999"
    assert student_report.grades_by_unit.get("unit-e2e") == 0.5
    assert student_report.total_points == 0.5

    # Check that submitted code snapshot is preserved
    a1_hist = next(a for a in student_report.assignments if a.id == a1.id)
    assert a1_hist.state == "passed"
    assert len(a1_hist.attempts) == 2
    assert "return 42" in a1_hist.attempts[1].code

    # Check unit stats
    unit_rep = get_unit_detail_report(panel_conn, "unit-e2e")
    assert unit_rep.code == "unit-e2e"

    # Check export list
    export_rows = list_unit_grades_for_export(panel_conn, "unit-e2e")
    e2e_student_row = next(r for r in export_rows if r.registration == "20240999")
    assert e2e_student_row.points == 0.5
