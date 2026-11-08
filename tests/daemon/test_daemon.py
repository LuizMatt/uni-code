import io
import socket
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

from tests.support import ROOT, TEST_DAEMON_URL, TEST_OWNER_URL
from unicode.config import Settings
from unicode.daemon.client import (
    DaemonClient,
    DaemonConnectionError,
    DaemonRemoteError,
)
from unicode.daemon.protocol import (
    MAX_MESSAGE_BYTES,
    DaemonRequest,
    DaemonResponse,
    deserialize_question_status,
    deserialize_student_feedback,
    encode_request,
    encode_response,
    parse_request_line,
    parse_response_line,
    serialize_question_status,
    serialize_student_feedback,
)
from unicode.daemon.server import (
    create_daemon_server,
    dispatch_request,
    initialize_daemon_state,
)
from unicode.db import DictConnection
from unicode.models import (
    Assignment,
    Attempt,
    DrawResult,
    QuestionStatus,
    SandboxResult,
    Session,
    StudentFeedback,
    SubmissionResult,
)
from unicode.services.questions import scan_and_validate_questions_dir, sync_questions
from unicode.services.sessions import SessionAuthError, create_session


class FakeRunner:
    def __init__(self, result: SandboxResult) -> None:
        self.result = result

    def run(self, code: str, test_eval_path: Path) -> SandboxResult:
        return self.result


def test_protocol_roundtrip_and_serializers() -> None:
    req = DaemonRequest(token="tok-123", action="start", payload={"unit_code": "unit-01"})
    parsed_req = parse_request_line(encode_request(req))
    assert parsed_req == req

    qs = QuestionStatus(
        unit_code="unit-01",
        question_slug="soma-dois-numeros",
        question_title="Soma de Dois Números",
        round=1,
        state="pending",
        points=Decimal("0.0"),
        attempts_used=1,
        attempts_remaining=2,
    )
    assert deserialize_question_status(serialize_question_status(qs)) == qs

    fb = StudentFeedback(
        status="failed",
        tests_total=3,
        tests_passed=2,
        attempt_number=1,
        attempts_remaining=2,
        assignment_state="pending",
        points=Decimal("0.0"),
        first_failed_test="test_negativos",
    )
    serialized_fb = serialize_student_feedback(fb)
    assert "output" not in serialized_fb
    assert "diagnostic_output" not in serialized_fb
    assert deserialize_student_feedback(serialized_fb) == fb

    resp = DaemonResponse(ok=True, data={"feedback": serialized_fb})
    parsed_resp = parse_response_line(encode_response(resp))
    assert parsed_resp.ok is True
    assert parsed_resp.data == {"feedback": serialized_fb}


def test_protocol_rejects_oversized_or_malformed_requests() -> None:
    oversized = b"x" * (MAX_MESSAGE_BYTES + 10)
    resp = dispatch_request(oversized)
    assert resp.ok is False
    assert resp.error is not None
    assert resp.error.code == "invalid_request"

    bad_json = dispatch_request(b"{not-json}\n")
    assert bad_json.ok is False
    assert bad_json.error is not None
    assert bad_json.error.code == "invalid_request"


def test_client_connection_error_on_unreachable_port() -> None:
    client = DaemonClient(endpoint="tcp://127.0.0.1:59999", timeout=1.0)
    with pytest.raises(DaemonConnectionError):
        client.get_status("tok")


def test_daemon_server_and_client_offline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import unicode.daemon.server as srv_mod

    now = datetime.now(UTC)
    fake_conn = object()

    @contextmanager
    def fake_tx(_pool: Any = None) -> Iterator[Any]:
        yield fake_conn

    monkeypatch.setattr(srv_mod, "transaction", fake_tx)
    monkeypatch.setattr(srv_mod, "recover_stale_attempts", lambda _conn: [])
    monkeypatch.setattr(srv_mod, "cleanup_expired_sessions", lambda _conn: 2)

    recovered, expired = initialize_daemon_state()
    assert recovered == 0
    assert expired == 2

    def fake_auth(_conn: Any, token: str) -> Session:
        if token != "valid-tok":
            raise SessionAuthError("sessão inválida ou expirada")
        return Session(
            student_registration="2026001",
            created_at=now,
            expires_at=now + timedelta(hours=4),
        )

    fake_assignment = Assignment(
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
    )
    current_status = QuestionStatus(
        unit_code="unit-01",
        question_slug="soma-dois-numeros",
        question_title="Soma de Dois Números",
        round=1,
        state="pending",
        points=Decimal("0.0"),
        attempts_used=0,
        attempts_remaining=3,
    )

    def fake_draw(_conn: Any, reg: str, unit_code: str, *, actor: str | None = None) -> DrawResult:
        return DrawResult(
            student_registration=reg,
            unit_code=unit_code,
            assignments=[fake_assignment],
            created=True,
        )

    def fake_status(
        _conn: Any, reg: str, *, unit_code: str | None = None
    ) -> list[QuestionStatus]:
        return [current_status]

    def fake_resolve(_conn: Any, reg: str, slug: str) -> str:
        return "unit-01"

    def fake_submit(
        reg: str,
        unit_code: str,
        slug: str,
        code: str,
        **_kwargs: Any,
    ) -> SubmissionResult:
        nonlocal current_status
        current_status = QuestionStatus(
            unit_code=unit_code,
            question_slug=slug,
            question_title="Soma de Dois Números",
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
                output="SECRET",
                finished_at=now,
            ),
            assignment=fake_assignment,
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

    settings = Settings(
        questions_dir=ROOT / "questions",
        workspaces_dir=tmp_path / "workspaces",
    )

    server = create_daemon_server("tcp://127.0.0.1:0", settings=settings)
    srv_addr = server.server_address
    assert isinstance(srv_addr, tuple)
    host, port = srv_addr[0], srv_addr[1]
    endpoint = f"tcp://{host!s}:{port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # Check if the environment blocks loopback socket.connect (e.g. restricted sandbox)
        can_connect = True
        try:
            with socket.create_connection((str(host), int(port)), timeout=1.0):
                pass
        except PermissionError:
            can_connect = False

        if not can_connect:
            class _LoopbackSocket:
                def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                    self._resp_bytes = b""

                def __enter__(self) -> "_LoopbackSocket":
                    return self

                def __exit__(self, *_args: Any) -> None:
                    pass

                def settimeout(self, _timeout: float) -> None:
                    pass

                def connect(self, _addr: Any) -> None:
                    pass

                def sendall(self, data: bytes) -> None:
                    resp = dispatch_request(data, settings=settings)
                    self._resp_bytes = encode_response(resp)

                def makefile(self, _mode: str) -> io.BytesIO:
                    return io.BytesIO(self._resp_bytes)

            monkeypatch.setattr(socket, "socket", _LoopbackSocket)

        client = DaemonClient(endpoint=endpoint, timeout=5.0)

        with pytest.raises(DaemonRemoteError) as exc_info:
            client.get_status("bad-tok")
        assert exc_info.value.code == "auth_error"

        created, questions = client.start_unit("valid-tok", "unit-01")
        assert created is True
        assert len(questions) == 1
        assert questions[0].question_slug == "soma-dois-numeros"
        assert (
            settings.workspaces_dir / "2026001" / "unit-01" / "soma-dois-numeros" / "solution.py"
        ).exists()

        res_unit, res_slug, feedback = client.submit(
            "valid-tok",
            "soma-dois-numeros",
            "def soma(a, b): return a + b\n",
        )
        assert res_unit == "unit-01"
        assert res_slug == "soma-dois-numeros"
        assert feedback.status == "passed"
        assert feedback.points == Decimal("0.5")

        statuses = client.get_status("valid-tok", unit_code="unit-01")
        assert len(statuses) == 1
        assert statuses[0].state == "passed"
        assert statuses[0].points == Decimal("0.5")
    finally:
        server.shutdown()
        server.server_close()


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


@pytest.mark.db
def test_daemon_server_and_client_end_to_end(
    clean_daemon_pool: ConnectionPool[DictConnection],
    tmp_path: Path,
) -> None:
    scanned = scan_and_validate_questions_dir(ROOT / "questions")
    with clean_daemon_pool.connection() as conn, conn.transaction():
        sync_questions(conn, scanned)
        conn.execute(
            "INSERT INTO students (registration, email, name) "
            "VALUES ('2026001', 'aluno@uni.edu', 'Aluno Teste')"
        )
        issued = create_session(conn, "2026001", ttl_seconds=3600)

    settings = Settings(
        questions_dir=ROOT / "questions",
        workspaces_dir=tmp_path / "workspaces",
    )
    runner = FakeRunner(
        SandboxResult(
            outcome="passed",
            tests_total=3,
            tests_passed=3,
            diagnostic_output="INTERNAL SECRET TRACEBACK",
        )
    )

    recovered_count, expired_count = initialize_daemon_state(pool=clean_daemon_pool)
    assert recovered_count == 0
    assert expired_count == 0

    server = create_daemon_server(
        "tcp://127.0.0.1:0",
        settings=settings,
        pool=clean_daemon_pool,
        runner=runner,
    )
    srv_addr = server.server_address
    assert isinstance(srv_addr, tuple)
    host, port = srv_addr[0], srv_addr[1]
    endpoint = f"tcp://{host!s}:{port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = DaemonClient(endpoint=endpoint, timeout=5.0)

        # Invalid session token is rejected with auth_error
        with pytest.raises(DaemonRemoteError) as exc_info:
            client.get_status("invalid-token")
        assert exc_info.value.code == "auth_error"

        # 1. Start unit-01
        created, questions = client.start_unit(issued.token, "unit-01")
        assert created is True
        assert len(questions) == 2
        slug_1 = questions[0].question_slug
        assert (settings.workspaces_dir / "2026001" / "unit-01" / slug_1 / "solution.py").exists()

        # 2. Submit solution without specifying unit_code (auto-resolved by daemon)
        res_unit, res_slug, feedback = client.submit(
            issued.token,
            slug_1,
            "def f(): return 1\n",
        )
        assert res_unit == "unit-01"
        assert res_slug == slug_1
        assert feedback.status == "passed"
        assert feedback.points == Decimal("0.5")
        assert feedback.attempts_remaining == 0

        # 3. Verify status reflects 0.5 points
        statuses = client.get_status(issued.token, unit_code="unit-01")
        by_slug = {s.question_slug: s for s in statuses}
        assert by_slug[slug_1].state == "passed"
        assert by_slug[slug_1].points == Decimal("0.5")
        assert by_slug[slug_1].attempts_used == 1
        assert by_slug[slug_1].attempts_remaining == 0
    finally:
        server.shutdown()
        server.server_close()
