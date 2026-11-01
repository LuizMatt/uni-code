import os
import socket
import socketserver
from pathlib import Path
from typing import Any

from psycopg_pool import ConnectionPool

from unicode.config import Settings, get_settings
from unicode.daemon.protocol import (
    MAX_MESSAGE_BYTES,
    DaemonErrorInfo,
    DaemonResponse,
    ProtocolError,
    encode_response,
    parse_endpoint,
    parse_request_line,
    serialize_question_status,
    serialize_student_feedback,
)
from unicode.db import DictConnection, transaction
from unicode.sandbox.runner import SandboxRunner
from unicode.services.assignments import (
    AssignmentError,
    NoActiveAssignmentsError,
    StudentNotFoundError,
    UnitNotFoundError,
    draw_assignments,
    get_student_status,
    provision_workspace,
    resolve_student_question_unit,
)
from unicode.services.sessions import (
    SessionAuthError,
    authenticate_session,
    cleanup_expired_sessions,
)
from unicode.services.submissions import (
    AssignmentNotFoundError,
    QuestionTestNotFoundError,
    SubmissionError,
    recover_stale_attempts,
    submit_solution,
)


def initialize_daemon_state(
    *,
    pool: ConnectionPool[DictConnection] | None = None,
) -> tuple[int, int]:
    """Recover stale running attempts and delete expired sessions at daemon startup."""
    with transaction(pool) as conn:
        recovered = recover_stale_attempts(conn)
        expired = cleanup_expired_sessions(conn)
    return (len(recovered), expired)


def dispatch_request(
    raw_line: bytes | str,
    *,
    settings: Settings | None = None,
    pool: ConnectionPool[DictConnection] | None = None,
    runner: SandboxRunner | None = None,
) -> DaemonResponse:
    """Authenticate and execute a single NDJSON daemon request."""
    try:
        req = parse_request_line(raw_line)
    except ProtocolError as exc:
        return DaemonResponse(
            ok=False,
            error=DaemonErrorInfo(code="invalid_request", message=str(exc)),
        )

    cfg = settings if settings is not None else get_settings()

    try:
        with transaction(pool) as conn:
            session = authenticate_session(conn, req.token)

        registration = session.student_registration

        if req.action == "start":
            unit_code = str(req.payload.get("unit_code") or "").strip()
            if not unit_code:
                return DaemonResponse(
                    ok=False,
                    error=DaemonErrorInfo(
                        code="invalid_request",
                        message="campo 'unit_code' é obrigatório",
                    ),
                )
            with transaction(pool) as conn:
                draw = draw_assignments(
                    conn,
                    registration,
                    unit_code,
                    actor=f"student:{registration}",
                )
                statuses = get_student_status(conn, registration, unit_code=unit_code)

            provision_workspace(
                cfg.workspaces_dir,
                cfg.questions_dir,
                draw.assignments,
            )
            return DaemonResponse(
                ok=True,
                data={
                    "unit_code": unit_code,
                    "created": draw.created,
                    "questions": [serialize_question_status(s) for s in statuses],
                },
            )

        if req.action == "status":
            raw_unit = req.payload.get("unit_code")
            unit_code_opt = str(raw_unit).strip() if raw_unit else None
            with transaction(pool) as conn:
                statuses = get_student_status(
                    conn,
                    registration,
                    unit_code=unit_code_opt,
                )
            return DaemonResponse(
                ok=True,
                data={
                    "questions": [serialize_question_status(s) for s in statuses],
                },
            )

        if req.action == "submit":
            question_slug = str(req.payload.get("question_slug") or "").strip()
            code = req.payload.get("code")
            raw_unit = req.payload.get("unit_code")
            unit_code_opt = str(raw_unit).strip() if raw_unit else None

            if not question_slug or not isinstance(code, str):
                return DaemonResponse(
                    ok=False,
                    error=DaemonErrorInfo(
                        code="invalid_request",
                        message="campos 'question_slug' e 'code' são obrigatórios",
                    ),
                )

            if unit_code_opt is None:
                with transaction(pool) as conn:
                    resolved_unit = resolve_student_question_unit(
                        conn,
                        registration,
                        question_slug,
                    )
            else:
                resolved_unit = unit_code_opt

            sub_result = submit_solution(
                registration,
                resolved_unit,
                question_slug,
                code,
                questions_dir=cfg.questions_dir,
                runner=runner,
                pool=pool,
                actor=f"student:{registration}",
            )
            return DaemonResponse(
                ok=True,
                data={
                    "unit_code": resolved_unit,
                    "question_slug": question_slug,
                    "feedback": serialize_student_feedback(sub_result.feedback),
                },
            )

        return DaemonResponse(
            ok=False,
            error=DaemonErrorInfo(code="invalid_request", message="ação desconhecida"),
        )
    except SessionAuthError as exc:
        return DaemonResponse(
            ok=False,
            error=DaemonErrorInfo(code="auth_error", message=str(exc)),
        )
    except (
        StudentNotFoundError,
        UnitNotFoundError,
        NoActiveAssignmentsError,
        AssignmentNotFoundError,
        QuestionTestNotFoundError,
    ) as exc:
        return DaemonResponse(
            ok=False,
            error=DaemonErrorInfo(code="not_found", message=str(exc)),
        )
    except (AssignmentError, SubmissionError) as exc:
        return DaemonResponse(
            ok=False,
            error=DaemonErrorInfo(code="business_error", message=str(exc)),
        )
    except Exception:
        return DaemonResponse(
            ok=False,
            error=DaemonErrorInfo(
                code="internal_error",
                message="erro interno no servidor",
            ),
        )


class _DaemonRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw_line = self.rfile.readline(MAX_MESSAGE_BYTES + 1)
        if not raw_line:
            return
        srv: Any = self.server
        resp = dispatch_request(
            raw_line,
            settings=getattr(srv, "unicode_settings", None),
            pool=getattr(srv, "unicode_pool", None),
            runner=getattr(srv, "unicode_runner", None),
        )
        self.wfile.write(encode_response(resp))
        self.wfile.flush()


class _ThreadingTCPDaemonServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def create_daemon_server(
    endpoint: str | Path | None = None,
    *,
    settings: Settings | None = None,
    pool: ConnectionPool[DictConnection] | None = None,
    runner: SandboxRunner | None = None,
) -> socketserver.BaseServer:
    """Create a threaded daemon server bound to a Unix socket or TCP loopback address."""
    cfg = settings if settings is not None else get_settings()
    target = endpoint if endpoint is not None else cfg.daemon_socket_path
    kind, addr = parse_endpoint(target)

    if kind == "tcp":
        assert isinstance(addr, tuple)
        server: socketserver.BaseServer = _ThreadingTCPDaemonServer(
            addr,
            _DaemonRequestHandler,
        )
    else:
        assert isinstance(addr, str)
        if not hasattr(socket, "AF_UNIX") or not hasattr(
            socketserver, "ThreadingUnixStreamServer"
        ):
            raise RuntimeError(
                "Sockets AF_UNIX não são suportados nesta plataforma; "
                "use um endpoint 'tcp://127.0.0.1:<porta>'."
            )
        sock_path = Path(addr)
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        if sock_path.exists():
            sock_path.unlink()
        unix_cls = getattr(socketserver, "ThreadingUnixStreamServer")  # noqa: B009
        server = unix_cls(str(sock_path), _DaemonRequestHandler)
        setattr(server, "daemon_threads", True)  # noqa: B010
        os.chmod(sock_path, 0o660)

    server.unicode_settings = cfg  # type: ignore[attr-defined]
    server.unicode_pool = pool  # type: ignore[attr-defined]
    server.unicode_runner = runner  # type: ignore[attr-defined]
    return server
