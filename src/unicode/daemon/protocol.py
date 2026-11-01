import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast

from unicode.models.assignment import AssignmentState, QuestionStatus
from unicode.models.attempt import FeedbackStatus, StudentFeedback

MAX_MESSAGE_BYTES = 262_144
DaemonAction = Literal["start", "status", "submit"]
_VALID_ACTIONS: set[str] = {"start", "status", "submit"}


def parse_endpoint(endpoint: str | Path) -> tuple[str, str | tuple[str, int]]:
    """Parse an endpoint into ('tcp', (host, port)) or ('unix', path_str)."""
    raw = str(endpoint).strip()
    if raw.startswith("tcp:") or raw.startswith("tcp://"):
        addr = raw[len("tcp:") :].lstrip("/\\")
        host, sep, port_str = addr.rpartition(":")
        if not sep or not host:
            raise ValueError(f"endpoint TCP inválido: {raw}")
        return ("tcp", (host, int(port_str)))
    return ("unix", raw)


class ProtocolError(Exception):
    """Raised when an IPC frame is malformed or exceeds size limits."""


@dataclass(frozen=True, slots=True)
class DaemonRequest:
    token: str
    action: DaemonAction
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DaemonErrorInfo:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class DaemonResponse:
    ok: bool
    data: dict[str, Any] | None = None
    error: DaemonErrorInfo | None = None


def parse_request_line(raw_line: bytes | str) -> DaemonRequest:
    raw_bytes = raw_line.encode("utf-8") if isinstance(raw_line, str) else raw_line
    if len(raw_bytes) > MAX_MESSAGE_BYTES:
        raise ProtocolError("mensagem excede o tamanho máximo permitido (256 KB)")
    try:
        text = raw_bytes.decode("utf-8").strip()
        parsed = json.loads(text)
    except Exception as exc:
        raise ProtocolError("requisição JSON malformada") from exc

    if not isinstance(parsed, dict):
        raise ProtocolError("requisição deve ser um objeto JSON")

    token = parsed.get("token")
    action = parsed.get("action")
    payload = parsed.get("payload", {})

    if not isinstance(token, str):
        raise ProtocolError("campo 'token' deve ser uma string")
    if not isinstance(action, str) or action not in _VALID_ACTIONS:
        raise ProtocolError(f"ação inválida: {action!r}")
    if not isinstance(payload, dict):
        raise ProtocolError("campo 'payload' deve ser um objeto JSON")

    return DaemonRequest(
        token=token,
        action=cast(DaemonAction, action),
        payload=payload,
    )


def encode_request(req: DaemonRequest) -> bytes:
    body = {
        "token": req.token,
        "action": req.action,
        "payload": req.payload,
    }
    return (json.dumps(body, ensure_ascii=False) + "\n").encode("utf-8")


def parse_response_line(raw_line: bytes | str) -> DaemonResponse:
    raw_bytes = raw_line.encode("utf-8") if isinstance(raw_line, str) else raw_line
    try:
        text = raw_bytes.decode("utf-8").strip()
        parsed = json.loads(text)
    except Exception as exc:
        raise ProtocolError("resposta JSON do daemon malformada") from exc

    if not isinstance(parsed, dict) or not isinstance(parsed.get("ok"), bool):
        raise ProtocolError("envelope de resposta do daemon inválido")

    ok = bool(parsed["ok"])
    data = parsed.get("data")
    err_raw = parsed.get("error")
    err_info: DaemonErrorInfo | None = None
    if isinstance(err_raw, dict):
        err_info = DaemonErrorInfo(
            code=str(err_raw.get("code", "unknown_error")),
            message=str(err_raw.get("message", "erro desconhecido")),
        )
    return DaemonResponse(
        ok=ok,
        data=data if isinstance(data, dict) else None,
        error=err_info,
    )


def encode_response(resp: DaemonResponse) -> bytes:
    body: dict[str, Any] = {"ok": resp.ok}
    if resp.data is not None:
        body["data"] = resp.data
    if resp.error is not None:
        body["error"] = {
            "code": resp.error.code,
            "message": resp.error.message,
        }
    return (json.dumps(body, ensure_ascii=False) + "\n").encode("utf-8")


def serialize_question_status(qs: QuestionStatus) -> dict[str, Any]:
    return {
        "unit_code": qs.unit_code,
        "question_slug": qs.question_slug,
        "question_title": qs.question_title,
        "round": qs.round,
        "state": qs.state,
        "points": str(qs.points),
        "attempts_used": qs.attempts_used,
        "attempts_remaining": qs.attempts_remaining,
    }


def deserialize_question_status(data: dict[str, Any]) -> QuestionStatus:
    return QuestionStatus(
        unit_code=str(data["unit_code"]),
        question_slug=str(data["question_slug"]),
        question_title=str(data["question_title"]),
        round=int(data["round"]),
        state=cast(AssignmentState, str(data["state"])),
        points=Decimal(str(data["points"])),
        attempts_used=int(data["attempts_used"]),
        attempts_remaining=int(data["attempts_remaining"]),
    )


def serialize_student_feedback(fb: StudentFeedback) -> dict[str, Any]:
    return {
        "status": fb.status,
        "tests_total": fb.tests_total,
        "tests_passed": fb.tests_passed,
        "attempt_number": fb.attempt_number,
        "attempts_remaining": fb.attempts_remaining,
        "assignment_state": fb.assignment_state,
        "points": str(fb.points),
        "first_failed_test": fb.first_failed_test,
        "error_category": fb.error_category,
    }


def deserialize_student_feedback(data: dict[str, Any]) -> StudentFeedback:
    first_failed = data.get("first_failed_test")
    err_cat = data.get("error_category")
    return StudentFeedback(
        status=cast(FeedbackStatus, str(data["status"])),
        tests_total=int(data["tests_total"]),
        tests_passed=int(data["tests_passed"]),
        attempt_number=int(data["attempt_number"]),
        attempts_remaining=int(data["attempts_remaining"]),
        assignment_state=cast(AssignmentState, str(data["assignment_state"])),
        points=Decimal(str(data["points"])),
        first_failed_test=str(first_failed) if first_failed is not None else None,
        error_category=str(err_cat) if err_cat is not None else None,
    )
