import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from unicode.db import DictConnection
from unicode.models import IssuedSession, Session
from unicode.services.assignments import StudentNotFoundError
from unicode.services.sessions import (
    InvalidCredentialsError,
    LoginRateLimitError,
    SessionAuthError,
    authenticate_session,
    authenticate_student_login,
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
        self.student_emails: dict[str, str] = {"2026001": "aluno@uni.edu"}
        self.sessions: dict[bytes, dict[str, Any]] = {}
        self.audit_logs: list[dict[str, Any]] = []
        self.now = datetime.now(UTC)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> FakeCursor:
        norm = " ".join(sql.split())
        if "pg_advisory_xact_lock" in norm:
            return FakeCursor(fetchone_val={"pg_advisory_xact_lock": None})

        if "FROM audit_log" in norm and "action = 'login_failed'" in norm:
            norm_ip = str(params[1])
            cnt = sum(
                1
                for log in self.audit_logs
                if log.get("action") == "login_failed"
                and json.loads(log["details"]).get("ip") == norm_ip
            )
            return FakeCursor(fetchone_val={"cnt": cnt})

        if "SELECT registration, email FROM students WHERE registration = %s" in norm:
            reg = str(params[0])
            if reg in self.student_emails:
                return FakeCursor(
                    fetchone_val={"registration": reg, "email": self.student_emails[reg]}
                )
            return FakeCursor(fetchone_val=None)

        if "FROM students WHERE registration = %s" in norm:
            reg = str(params[0])
            if reg in self.students or reg in self.student_emails:
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


def test_authenticate_student_login_success_and_failures_unit() -> None:
    conn = FakeSessionConn()

    # Valid login (case-insensitive email, trimmed inputs)
    issued = authenticate_student_login(
        conn,  # type: ignore[arg-type]
        "  ALUNO@uni.edu ",
        " 2026001 ",
        client_ip="10.0.0.1",
        ttl_seconds=3600,
    )
    assert issued.session.student_registration == "2026001"
    assert any(log["action"] == "login" for log in conn.audit_logs)

    # Wrong email -> generic message + login_failed audit log
    with pytest.raises(InvalidCredentialsError, match="^credenciais inválidas$"):
        authenticate_student_login(
            conn,  # type: ignore[arg-type]
            "errado@uni.edu",
            "2026001",
            client_ip="10.0.0.2",
        )

    # Unknown registration -> same generic message + login_failed audit log
    with pytest.raises(InvalidCredentialsError, match="^credenciais inválidas$"):
        authenticate_student_login(
            conn,  # type: ignore[arg-type]
            "aluno@uni.edu",
            "9999999",
            client_ip="10.0.0.2",
        )

    # Empty inputs -> same generic message
    with pytest.raises(InvalidCredentialsError, match="^credenciais inválidas$"):
        authenticate_student_login(
            conn,  # type: ignore[arg-type]
            "   ",
            "2026001",
            client_ip="10.0.0.2",
        )


def test_authenticate_student_login_rate_limit_by_ip_unit() -> None:
    conn = FakeSessionConn()
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            authenticate_student_login(
                conn,  # type: ignore[arg-type]
                "wrong@uni.edu",
                "2026001",
                client_ip="192.168.1.50",
                max_failures=5,
                window_seconds=60,
            )

    # 6th attempt from same IP is blocked even with valid credentials
    with pytest.raises(LoginRateLimitError, match="^credenciais inválidas$"):
        authenticate_student_login(
            conn,  # type: ignore[arg-type]
            "aluno@uni.edu",
            "2026001",
            client_ip="192.168.1.50",
            max_failures=5,
            window_seconds=60,
        )

    # Another IP is unaffected
    issued = authenticate_student_login(
        conn,  # type: ignore[arg-type]
        "aluno@uni.edu",
        "2026001",
        client_ip="192.168.1.51",
        max_failures=5,
        window_seconds=60,
    )
    assert issued.session.student_registration == "2026001"


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


@pytest.mark.db
def test_authenticate_student_login_and_rate_limit_db(daemon_conn: DictConnection) -> None:
    daemon_conn.execute(
        "INSERT INTO students (registration, email, name) "
        "VALUES ('0020261', 'Maria.Silva@instituicao.edu.br', 'Maria')"
    )

    # Successful login with leading zero registration and mixed-case email
    issued = authenticate_student_login(
        daemon_conn,
        "  maria.silva@instituicao.edu.br ",
        "0020261",
        client_ip="203.0.113.10",
        ttl_seconds=1800,
    )
    assert issued.session.student_registration == "0020261"

    # 5 failed attempts from 203.0.113.99
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError, match="^credenciais inválidas$"):
            authenticate_student_login(
                daemon_conn,
                "invalido@instituicao.edu.br",
                "0020261",
                client_ip="203.0.113.99",
                max_failures=5,
                window_seconds=60,
            )

    # 6th attempt from 203.0.113.99 fails with LoginRateLimitError even with right credentials
    with pytest.raises(LoginRateLimitError, match="^credenciais inválidas$"):
        authenticate_student_login(
            daemon_conn,
            "maria.silva@instituicao.edu.br",
            "0020261",
            client_ip="203.0.113.99",
            max_failures=5,
            window_seconds=60,
        )

    rate_limited_row = daemon_conn.execute(
        "SELECT COUNT(*) AS cnt FROM audit_log "
        "WHERE action = 'login_rate_limited' AND details ->> 'ip' = '203.0.113.99'"
    ).fetchone()
    assert rate_limited_row is not None
    assert int(rate_limited_row["cnt"]) == 1
