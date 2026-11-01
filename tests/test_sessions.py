from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from unicode.db import DictConnection
from unicode.models import IssuedSession, Session
from unicode.services.assignments import StudentNotFoundError
from unicode.services.sessions import (
    SessionAuthError,
    authenticate_session,
    cleanup_expired_sessions,
    create_session,
    hash_session_token,
    revoke_session,
)


class FakeCursor:
    def __init__(
        self,
        fetchone_val: dict[str, Any] | None = None,
        rowcount: int = 0,
    ) -> None:
        self._fetchone_val = fetchone_val
        self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._fetchone_val


class FakeSessionConn:
    def __init__(self) -> None:
        self.students: set[str] = {"2026001"}
        self.sessions: dict[bytes, dict[str, Any]] = {}
        self.audit_logs: list[dict[str, Any]] = []
        self.now = datetime.now(UTC)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> FakeCursor:
        norm = " ".join(sql.split())
        if "FROM students WHERE registration = %s" in norm:
            reg = str(params[0])
            if reg in self.students:
                return FakeCursor(fetchone_val={"registration": reg})
            return FakeCursor(fetchone_val=None)

        if "INSERT INTO sessions" in norm:
            th = bytes(params[0])
            reg = str(params[1])
            ttl = int(params[2])
            row = {
                "token_hash": th,
                "student_registration": reg,
                "created_at": self.now,
                "expires_at": self.now + timedelta(seconds=ttl),
            }
            self.sessions[th] = row
            return FakeCursor(fetchone_val=row, rowcount=1)

        if "INSERT INTO audit_log" in norm:
            self.audit_logs.append(
                {"actor": params[0], "action": params[1], "details": params[2]}
            )
            return FakeCursor(rowcount=1)

        if "FROM sessions WHERE token_hash = %s AND expires_at > now()" in norm:
            th = bytes(params[0])
            s = self.sessions.get(th)
            if s is not None and s["expires_at"] > self.now:
                return FakeCursor(fetchone_val=s)
            return FakeCursor(fetchone_val=None)

        if "DELETE FROM sessions WHERE token_hash = %s" in norm:
            th = bytes(params[0])
            existed = self.sessions.pop(th, None) is not None
            return FakeCursor(rowcount=1 if existed else 0)

        if "DELETE FROM sessions WHERE expires_at <= now()" in norm:
            expired = [k for k, v in self.sessions.items() if v["expires_at"] <= self.now]
            for k in expired:
                del self.sessions[k]
            return FakeCursor(rowcount=len(expired))

        raise AssertionError(f"Unexpected SQL: {norm}")


def test_hash_session_token_is_32_bytes_sha256() -> None:
    digest = hash_session_token("my-secret-token")
    assert isinstance(digest, bytes)
    assert len(digest) == 32
    assert digest == hash_session_token("my-secret-token")
    assert digest != hash_session_token("other-token")


def test_session_lifecycle_unit() -> None:
    conn = FakeSessionConn()
    issued = create_session(conn, "2026001", ttl_seconds=3600)  # type: ignore[arg-type]
    assert isinstance(issued, IssuedSession)
    assert len(issued.token) >= 32
    assert issued.session.student_registration == "2026001"

    authed = authenticate_session(conn, issued.token)  # type: ignore[arg-type]
    assert isinstance(authed, Session)
    assert authed.student_registration == "2026001"

    with pytest.raises(SessionAuthError, match="ausente"):
        authenticate_session(conn, "   ")  # type: ignore[arg-type]

    with pytest.raises(SessionAuthError, match="inválida ou expirada"):
        authenticate_session(conn, "wrong-token")  # type: ignore[arg-type]

    assert revoke_session(conn, issued.token) is True  # type: ignore[arg-type]
    assert revoke_session(conn, issued.token) is False  # type: ignore[arg-type]

    with pytest.raises(SessionAuthError):
        authenticate_session(conn, issued.token)  # type: ignore[arg-type]


def test_session_expiration_and_cleanup_unit() -> None:
    conn = FakeSessionConn()
    issued = create_session(conn, "2026001", ttl_seconds=60)  # type: ignore[arg-type]
    conn.now = conn.now + timedelta(seconds=61)

    with pytest.raises(SessionAuthError):
        authenticate_session(conn, issued.token)  # type: ignore[arg-type]

    removed = cleanup_expired_sessions(conn)  # type: ignore[arg-type]
    assert removed == 1


def test_create_session_rejects_unknown_student_and_invalid_ttl() -> None:
    conn = FakeSessionConn()
    with pytest.raises(StudentNotFoundError):
        create_session(conn, "9999999")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="positivo"):
        create_session(conn, "2026001", ttl_seconds=0)  # type: ignore[arg-type]


@pytest.mark.db
def test_sessions_db_integration(daemon_conn: DictConnection) -> None:
    daemon_conn.execute(
        "INSERT INTO students (registration, email, name) VALUES ('2026001', 'a@u.edu', 'Aluno')"
    )
    issued = create_session(daemon_conn, "2026001", ttl_seconds=1800)
    session = authenticate_session(daemon_conn, issued.token)
    assert session.student_registration == "2026001"

    # Raw token is never stored in DB, only its 32-byte sha256
    row = daemon_conn.execute(
        "SELECT token_hash FROM sessions WHERE student_registration = '2026001'"
    ).fetchone()
    assert row is not None
    assert bytes(row["token_hash"]) == hash_session_token(issued.token)

    assert revoke_session(daemon_conn, issued.token) is True
    with pytest.raises(SessionAuthError):
        authenticate_session(daemon_conn, issued.token)
