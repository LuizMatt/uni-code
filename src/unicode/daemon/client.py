import socket
from pathlib import Path
from typing import Any

from unicode.config import get_settings
from unicode.daemon.protocol import (
    MAX_MESSAGE_BYTES,
    DaemonAction,
    DaemonRequest,
    DaemonResponse,
    ProtocolError,
    deserialize_question_status,
    deserialize_student_feedback,
    encode_request,
    parse_endpoint,
    parse_response_line,
)
from unicode.models.assignment import QuestionStatus
from unicode.models.attempt import StudentFeedback


class DaemonClientError(Exception):
    """Base exception for student CLI -> daemon client errors."""


class DaemonConnectionError(DaemonClientError):
    """Raised when the daemon socket cannot be reached."""


class DaemonRemoteError(DaemonClientError):
    """Raised when the daemon returns ok=False."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DaemonClient:
    """Synchronous NDJSON client for unicode-daemon."""

    def __init__(
        self,
        endpoint: str | Path | None = None,
        *,
        timeout: float = 15.0,
    ) -> None:
        self._endpoint = (
            endpoint if endpoint is not None else get_settings().daemon_socket_path
        )
        self._timeout = timeout

    def request(
        self,
        token: str,
        action: DaemonAction,
        payload: dict[str, Any],
    ) -> DaemonResponse:
        req = DaemonRequest(token=token, action=action, payload=payload)
        raw_req = encode_request(req)
        kind, addr = parse_endpoint(self._endpoint)

        try:
            if kind == "tcp":
                assert isinstance(addr, tuple)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            else:
                if not hasattr(socket, "AF_UNIX"):
                    raise DaemonConnectionError(
                        "Sockets AF_UNIX não disponíveis nesta plataforma."
                    )
                sock = socket.socket(getattr(socket, "AF_UNIX"), socket.SOCK_STREAM)  # noqa: B009

            with sock:
                sock.settimeout(self._timeout)
                sock.connect(addr)
                sock.sendall(raw_req)
                with sock.makefile("rb") as rfile:
                    raw_resp = rfile.readline(MAX_MESSAGE_BYTES + 1)
        except DaemonClientError:
            raise
        except OSError as exc:
            raise DaemonConnectionError(
                f"não foi possível conectar ao unicode-daemon ({self._endpoint}): {exc}"
            ) from exc

        if not raw_resp:
            raise DaemonConnectionError("resposta vazia recebida do unicode-daemon")

        try:
            resp = parse_response_line(raw_resp)
        except ProtocolError as exc:
            raise DaemonClientError(str(exc)) from exc

        if not resp.ok:
            if resp.error is not None:
                raise DaemonRemoteError(resp.error.code, resp.error.message)
            raise DaemonRemoteError("unknown_error", "erro desconhecido no daemon")

        return resp

    def start_unit(
        self, token: str, unit_code: str
    ) -> tuple[bool, list[QuestionStatus]]:
        resp = self.request(token, "start", {"unit_code": unit_code})
        data = resp.data or {}
        created = bool(data.get("created", False))
        raw_questions = data.get("questions", [])
        questions = [
            deserialize_question_status(item)
            for item in raw_questions
            if isinstance(item, dict)
        ]
        return (created, questions)

    def get_status(
        self, token: str, *, unit_code: str | None = None
    ) -> list[QuestionStatus]:
        resp = self.request(token, "status", {"unit_code": unit_code})
        data = resp.data or {}
        raw_questions = data.get("questions", [])
        return [
            deserialize_question_status(item)
            for item in raw_questions
            if isinstance(item, dict)
        ]

    def submit(
        self,
        token: str,
        question_slug: str,
        code: str,
        *,
        unit_code: str | None = None,
    ) -> tuple[str, str, StudentFeedback]:
        resp = self.request(
            token,
            "submit",
            {
                "unit_code": unit_code,
                "question_slug": question_slug,
                "code": code,
            },
        )
        data = resp.data or {}
        resolved_unit = str(data.get("unit_code", unit_code or ""))
        resolved_slug = str(data.get("question_slug", question_slug))
        fb_raw = data.get("feedback")
        if not isinstance(fb_raw, dict):
            raise DaemonClientError("resposta de submissão sem feedback estruturado")
        return (resolved_unit, resolved_slug, deserialize_student_feedback(fb_raw))
