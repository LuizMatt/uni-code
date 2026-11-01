import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from typer.testing import CliRunner

from tests.support import ROOT, TEST_DAEMON_URL, TEST_OWNER_URL
from unicode.cli_student import (
    app,
    extract_readme_assert_blocks,
    resolve_local_question_files,
    run_local_public_examples,
)
from unicode.config import Settings
from unicode.daemon.client import DaemonClient
from unicode.daemon.protocol import DaemonAction, DaemonRequest, DaemonResponse, encode_request
from unicode.daemon.server import create_daemon_server, dispatch_request
from unicode.db import DictConnection
from unicode.models import (
    Assignment,
    Attempt,
    DrawResult,
    QuestionStatus,
    Session,
    StudentFeedback,
    SubmissionResult,
)
from unicode.models.sandbox import SandboxResult
from unicode.services.questions import scan_and_validate_questions_dir, sync_questions
from unicode.services.sessions import SessionAuthError, create_session

runner = CliRunner()


class FakeSandboxRunner:
    def __init__(self, result: SandboxResult) -> None:
        self.result = result

    def run(self, code: str, test_eval_path: Path) -> SandboxResult:
        return self.result


@pytest.fixture
def clean_daemon_pool(
    migrated_db: None,
) -> Iterator[ConnectionPool[DictConnection]]:
    with psycopg.connect(TEST_OWNER_URL) as owner:
        owner.execute(
            "TRUNCATE attempts, assignments, sessions, questions, units, students, audit_log "
            "RESTART IDENTITY CASCADE"
        )
    pool: ConnectionPool[DictConnection] = ConnectionPool(
        conninfo=TEST_DAEMON_URL,
        min_size=1,
        max_size=4,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    try:
        yield pool
    finally:
        pool.close()
        with psycopg.connect(TEST_OWNER_URL) as owner:
            owner.execute(
                "TRUNCATE attempts, assignments, sessions, questions, units, students, audit_log "
                "RESTART IDENTITY CASCADE"
            )


def test_extract_readme_assert_blocks_and_run_local_examples(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Soma\n\n```python\nassert soma(2, 3) == 5\nassert soma(-1, 1) == 0\n```\n",
        encoding="utf-8",
    )
    blocks = extract_readme_assert_blocks(readme.read_text(encoding="utf-8"))
    assert len(blocks) == 1

    sol = tmp_path / "solution.py"
    sol.write_text("def soma(a: int, b: int) -> int:\n    return 0\n", encoding="utf-8")
    ok_fail, count_fail, out_fail = run_local_public_examples(sol, readme)
    assert ok_fail is False
    assert count_fail == 2
    assert "assert soma(2, 3) == 5" in out_fail

    sol.write_text("def soma(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    ok_pass, count_pass, out_pass = run_local_public_examples(sol, readme)
    assert ok_pass is True
    assert count_pass == 2
    assert "PASSOU" in out_pass


def test_run_local_public_examples_supports_local_pytest_files(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Sem asserts no README\n", encoding="utf-8")
    sol = tmp_path / "solution.py"
    sol.write_text("def dobro(x: int) -> int:\n    return x * 2\n", encoding="utf-8")

    # Without asserts or test_*.py files, returns False with message
    ok_none, count_none, out_none = run_local_public_examples(sol, readme)
    assert ok_none is False
    assert count_none == 0
    assert "Nenhum exemplo público" in out_none

    # Add a local test_*.py file alongside solution.py
    local_test = tmp_path / "test_public.py"
    local_test.write_text(
        "from solution import dobro\n\n"
        "def test_dobro_basico() -> None:\n"
        "    assert dobro(3) == 6\n"
        "    assert dobro(0) == 0\n",
        encoding="utf-8",
    )
    ok_pytest, count_pytest, out_pytest = run_local_public_examples(sol, readme)
    assert ok_pytest is True
    assert count_pytest == 1
    assert "PASSOU" in out_pytest

    # Combined README.md asserts + local test_*.py file
    readme.write_text("# Dobro\n\n```python\nassert dobro(5) == 10\n```\n", encoding="utf-8")
    ok_both, count_both, out_both = run_local_public_examples(sol, readme)
    assert ok_both is True
    assert count_both == 2
    assert "Exemplo 1: assert dobro(5) == 10" in out_both
    assert "Resultado local (pytest): PASSOU" in out_both

    # If local test_*.py fails, returns False
    local_test.write_text(
        "from solution import dobro\n\n"
        "def test_dobro_falho() -> None:\n"
        "    assert dobro(3) == 999\n",
        encoding="utf-8",
    )
    ok_py_fail, _, out_py_fail = run_local_public_examples(sol, readme)
    assert ok_py_fail is False
    assert "FALHOU" in out_py_fail


def test_resolve_local_question_files_from_cwd_and_workspace(tmp_path: Path) -> None:
    q_dir = tmp_path / "unit-01" / "soma-dois-numeros"
    q_dir.mkdir(parents=True)
    sol = q_dir / "solution.py"
    readme = q_dir / "README.md"
    sol.write_text("def soma(a, b): return a + b\n", encoding="utf-8")
    readme.write_text("# Soma\n", encoding="utf-8")

    # 1. Inside the question folder with question_slug=None
    slug, unit, found_sol, found_readme = resolve_local_question_files(
        None,
        None,
        None,
        cwd=q_dir,
        workspace_dir=tmp_path,
    )
    assert slug == "soma-dois-numeros"
    assert unit == "unit-01"
    assert found_sol == sol
    assert found_readme == readme

    # 2. From workspace root passing only question_slug
    slug2, unit2, found_sol2, _ = resolve_local_question_files(
        "soma-dois-numeros",
        None,
        None,
        cwd=tmp_path,
        workspace_dir=tmp_path,
    )
    assert slug2 == "soma-dois-numeros"
    assert unit2 == "unit-01"
    assert found_sol2 == sol


def test_cli_missing_session_token_exits_with_code_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UNICODE_SESSION", raising=False)
    res = runner.invoke(app, ["status"])
    assert res.exit_code == 2
    assert "UNICODE_SESSION" in res.output


def test_student_cli_full_workflow_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import unicode.daemon.server as srv_mod

    now = datetime.now(UTC)
    fake_conn = object()

    @contextmanager
    def fake_tx(_pool: Any = None) -> Iterator[Any]:
        yield fake_conn

    monkeypatch.setattr(srv_mod, "transaction", fake_tx)

    def fake_auth(_conn: Any, token: str) -> Session:
        if token != "valid-tok":
            raise SessionAuthError("sessão inválida ou expirada")
        return Session(
            student_registration="2026001",
            created_at=now,
            expires_at=now + timedelta(hours=4),
        )

    fake_assignments = [
        Assignment(
            id=1,
            student_registration="2026001",
            unit_id=1,
            unit_code="unit-01",
            question_id=10,
            question_slug="soma-dois-numeros",
            round=1,
            state="pending",
            points=Decimal("0.0"),
            created_at=now,
        ),
        Assignment(
            id=2,
            student_registration="2026001",
            unit_id=1,
            unit_code="unit-01",
            question_id=11,
            question_slug="eh-par",
            round=1,
            state="pending",
            points=Decimal("0.0"),
            created_at=now,
        ),
    ]
    statuses_by_slug: dict[str, QuestionStatus] = {
        "soma-dois-numeros": QuestionStatus(
            unit_code="unit-01",
            question_slug="soma-dois-numeros",
            question_title="Soma de Dois Números",
            round=1,
            state="pending",
            points=Decimal("0.0"),
            attempts_used=0,
            attempts_remaining=3,
        ),
        "eh-par": QuestionStatus(
            unit_code="unit-01",
            question_slug="eh-par",
            question_title="Número Par",
            round=1,
            state="pending",
            points=Decimal("0.0"),
            attempts_used=0,
            attempts_remaining=3,
        ),
    }

    def fake_draw(_conn: Any, reg: str, unit_code: str, *, actor: str | None = None) -> DrawResult:
        return DrawResult(
            student_registration=reg,
            unit_code=unit_code,
            assignments=fake_assignments,
            created=True,
        )

    def fake_status(
        _conn: Any, reg: str, *, unit_code: str | None = None
    ) -> list[QuestionStatus]:
        return list(statuses_by_slug.values())

    def fake_resolve(_conn: Any, reg: str, slug: str) -> str:
        return "unit-01"

    def fake_submit(
        reg: str,
        unit_code: str,
        slug: str,
        code: str,
        **_kwargs: Any,
    ) -> SubmissionResult:
        statuses_by_slug[slug] = QuestionStatus(
            unit_code=unit_code,
            question_slug=slug,
            question_title=statuses_by_slug[slug].question_title,
            round=1,
            state="passed",
            points=Decimal("0.5"),
            attempts_used=1,
            attempts_remaining=0,
        )
        return SubmissionResult(
            attempt=Attempt(
                id=1,
                assignment_id=1,
                number=1,
                status="passed",
                code=code,
                started_at=now,
                tests_total=3,
                tests_passed=3,
                output="HIDDEN SECRET EVAL OUTPUT",
                finished_at=now,
            ),
            assignment=fake_assignments[0],
            feedback=StudentFeedback(
                status="passed",
                tests_total=3,
                tests_passed=3,
                attempt_number=1,
                attempts_remaining=0,
                assignment_state="passed",
                points=Decimal("0.5"),
            ),
        )

    monkeypatch.setattr(srv_mod, "authenticate_session", fake_auth)
    monkeypatch.setattr(srv_mod, "draw_assignments", fake_draw)
    monkeypatch.setattr(srv_mod, "get_student_status", fake_status)
    monkeypatch.setattr(srv_mod, "resolve_student_question_unit", fake_resolve)
    monkeypatch.setattr(srv_mod, "submit_solution", fake_submit)

    ws_root = tmp_path / "workspaces"
    student_ws = ws_root / "2026001"
    settings = Settings(
        questions_dir=ROOT / "questions",
        workspaces_dir=ws_root,
        student_workspace_dir=student_ws,
    )

    def fake_request(
        self: DaemonClient,
        token: str,
        action: DaemonAction,
        payload: dict[str, Any],
    ) -> DaemonResponse:
        req = DaemonRequest(token=token, action=action, payload=payload)
        resp = dispatch_request(encode_request(req), settings=settings)
        if not resp.ok:
            from unicode.daemon.client import DaemonRemoteError

            assert resp.error is not None
            raise DaemonRemoteError(resp.error.code, resp.error.message)
        return resp

    monkeypatch.setattr(DaemonClient, "request", fake_request)
    monkeypatch.setenv("UNICODE_SESSION", "valid-tok")
    monkeypatch.setenv("UNICODE_STUDENT_WORKSPACE_DIR", str(student_ws))

    # 1. Start unit-01
    r_start = runner.invoke(app, ["start", "unit-01"])
    assert r_start.exit_code == 0
    assert "unit-01" in r_start.output
    assert "soma-dois-numeros" in r_start.output

    target_slug = "soma-dois-numeros"
    target_q_dir = student_ws / "unit-01" / target_slug
    assert (target_q_dir / "solution.py").exists()

    # 2. Local test on initial template fails (exit code 1) and consumes 0 attempts
    r_test_fail = runner.invoke(app, ["test", target_slug])
    assert r_test_fail.exit_code == 1
    assert "não consome tentativa" in r_test_fail.output

    # Verify 0 attempts in status
    r_status_before = runner.invoke(app, ["status"])
    assert r_status_before.exit_code == 0
    assert "0/3 (3)" in r_status_before.output

    # 3. Empty file rejection on submit (exit code 1, does not consume attempt)
    sol_file = target_q_dir / "solution.py"
    sol_file.write_text("   \n", encoding="utf-8")
    r_submit_empty = runner.invoke(app, ["submit", target_slug])
    assert r_submit_empty.exit_code == 1
    assert "vazio" in r_submit_empty.output

    # 4. Write valid solution, test locally, and submit from inside question cwd without slug arg
    sol_file.write_text("def soma(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    monkeypatch.chdir(target_q_dir)

    r_test_pass = runner.invoke(app, ["test"])
    assert r_test_pass.exit_code == 0
    assert "PASSOU" in r_test_pass.output

    r_submit = runner.invoke(app, ["submit"])
    assert r_submit.exit_code == 0
    assert "APROVADA" in r_submit.output
    assert "3/3" in r_submit.output
    assert "0.5" in r_submit.output
    assert "HIDDEN SECRET EVAL OUTPUT" not in r_submit.output

    # 5. Status now shows passed and 0.5 points
    r_status_after = runner.invoke(app, ["status", "--unidade", "unit-01"])
    assert r_status_after.exit_code == 0
    assert "aprovada" in r_status_after.output
    assert "0.5" in r_status_after.output


@pytest.mark.db
def test_student_cli_full_workflow_with_daemon(
    clean_daemon_pool: ConnectionPool[DictConnection],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanned = scan_and_validate_questions_dir(ROOT / "questions")
    with clean_daemon_pool.connection() as conn, conn.transaction():
        sync_questions(conn, scanned)
        conn.execute(
            "INSERT INTO students (registration, email, name) "
            "VALUES ('2026001', 'aluno@uni.edu', 'Aluno CLI')"
        )
        issued = create_session(conn, "2026001", ttl_seconds=3600)

    ws_root = tmp_path / "workspaces"
    student_ws = ws_root / "2026001"
    settings = Settings(
        questions_dir=ROOT / "questions",
        workspaces_dir=ws_root,
        student_workspace_dir=student_ws,
    )
    sbx = FakeSandboxRunner(
        SandboxResult(
            outcome="passed",
            tests_total=3,
            tests_passed=3,
            diagnostic_output="HIDDEN SECRET EVAL OUTPUT",
        )
    )

    server = create_daemon_server(
        "tcp://127.0.0.1:0",
        settings=settings,
        pool=clean_daemon_pool,
        runner=sbx,
    )
    srv_addr = server.server_address
    assert isinstance(srv_addr, tuple)
    host, port = srv_addr[0], srv_addr[1]
    endpoint = f"tcp://{host!s}:{port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("UNICODE_SESSION", issued.token)
        monkeypatch.setenv("UNICODE_DAEMON_SOCKET_PATH", endpoint)
        monkeypatch.setenv("UNICODE_STUDENT_WORKSPACE_DIR", str(student_ws))

        # 1. Start unit-01
        r_start = runner.invoke(app, ["start", "unit-01"])
        assert r_start.exit_code == 0
        assert "unit-01" in r_start.output

        # Find drawn question slug
        unit_dir = student_ws / "unit-01"
        drawn_dirs = [p for p in unit_dir.iterdir() if p.is_dir()]
        assert len(drawn_dirs) == 2
        target_q_dir = drawn_dirs[0]
        target_slug = target_q_dir.name

        # 2. Local test on initial template fails (exit code 1) and consumes 0 attempts
        r_test_fail = runner.invoke(app, ["test", target_slug])
        assert r_test_fail.exit_code == 1
        assert "não consome tentativa" in r_test_fail.output

        # Verify 0 attempts in status
        r_status_before = runner.invoke(app, ["status"])
        assert r_status_before.exit_code == 0
        assert "0/3 (3)" in r_status_before.output

        # 3. Write real solution and submit
        sol_file = target_q_dir / "solution.py"
        sol_file.write_text("# valid solution\nx = 1\n", encoding="utf-8")

        r_submit = runner.invoke(app, ["submit", target_slug])
        assert r_submit.exit_code == 0
        assert "APROVADA" in r_submit.output
        assert "3/3" in r_submit.output
        assert "0.5" in r_submit.output
        assert "HIDDEN SECRET EVAL OUTPUT" not in r_submit.output

        # 4. Status now shows passed and 0.5 points
        r_status_after = runner.invoke(app, ["status", "--unidade", "unit-01"])
        assert r_status_after.exit_code == 0
        assert "aprovada" in r_status_after.output
        assert "0.5" in r_status_after.output
    finally:
        server.shutdown()
        server.server_close()
