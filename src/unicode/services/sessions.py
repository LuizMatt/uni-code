import hashlib
import json
import secrets
from datetime import datetime
from typing import Any, cast

from unicode.db import DictConnection
from unicode.models.session import IssuedSession, Session
from unicode.services.assignments import StudentNotFoundError


class SessionError(Exception):
    """Base exception for session operations."""


class SessionAuthError(SessionError):
    """Raised when a session token is missing, invalid, or expired."""


class LoginAuthError(SessionError):
    """Base exception for interactive student login failures."""


class InvalidCredentialsError(LoginAuthError):
    """Raised when login email or registration is invalid."""


class LoginRateLimitError(LoginAuthError):
    """Raised when the client IP has exceeded the maximum failed login attempts."""


def hash_session_token(token: str) -> bytes:
    """Return the 32-byte SHA-256 digest of a raw session token."""
    return hashlib.sha256(token.encode("utf-8")).digest()


def _constant_time_equals(left: str, right: str) -> bool:
    """Compare two strings in constant time using their 32-byte SHA-256 digests."""
    left_digest = hashlib.sha256(left.encode("utf-8")).digest()
    right_digest = hashlib.sha256(right.encode("utf-8")).digest()
    return secrets.compare_digest(left_digest, right_digest)


def _row_to_session(row: dict[str, Any]) -> Session:
    return Session(
        student_registration=str(row["student_registration"]),
        created_at=cast(datetime, row["created_at"]),
        expires_at=cast(datetime, row["expires_at"]),
    )


def create_session(
    conn: DictConnection,
    registration: str,
    *,
    ttl_seconds: int = 14400,
    actor: str | None = None,
) -> IssuedSession:
    """Create a new student session and store only the SHA-256 token hash."""
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds deve ser positivo")

    student_row = conn.execute(
        "SELECT registration FROM students WHERE registration = %s",
        (registration,),
    ).fetchone()
    if student_row is None:
        raise StudentNotFoundError(f"aluno '{registration}' não encontrado")

    token = secrets.token_urlsafe(32)
    token_hash = hash_session_token(token)

    row = conn.execute(
        "INSERT INTO sessions (token_hash, student_registration, expires_at) "
        "VALUES (%s, %s, now() + make_interval(secs => %s)) "
        "RETURNING student_registration, created_at, expires_at",
        (token_hash, registration, ttl_seconds),
    ).fetchone()
    assert row is not None

    audit_details = {
        "student_registration": registration,
        "ttl_seconds": ttl_seconds,
    }
    conn.execute(
        "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
        (actor or f"student:{registration}", "create_session", json.dumps(audit_details)),
    )

    return IssuedSession(token=token, session=_row_to_session(row))


def authenticate_student_login(
    conn: DictConnection,
    email: str,
    registration: str,
    *,
    client_ip: str = "local",
    ttl_seconds: int = 14400,
    max_failures: int = 5,
    window_seconds: int = 60,
) -> IssuedSession:
    """Authenticate student email + registration with constant-time compare and IP rate limit."""
    if max_failures < 1:
        raise ValueError("max_failures deve ser pelo menos 1")
    if window_seconds < 1:
        raise ValueError("window_seconds deve ser pelo menos 1")

    norm_ip = client_ip.strip() or "local"
    norm_email = email.strip().lower()
    norm_reg = registration.strip()

    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtext('login_ip'), hashtext(%s))",
        (norm_ip,),
    )

    fail_row = conn.execute(
        "SELECT COUNT(*) AS cnt "
        "FROM audit_log "
        "WHERE action = 'login_failed' "
        "AND occurred_at > now() - make_interval(secs => %s) "
        "AND details ->> 'ip' = %s",
        (window_seconds, norm_ip),
    ).fetchone()
    recent_failures = int(fail_row["cnt"]) if fail_row is not None else 0

    if recent_failures >= max_failures:
        conn.execute(
            "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
            (
                f"ip:{norm_ip}",
                "login_rate_limited",
                json.dumps({"ip": norm_ip, "attempted_registration": norm_reg}),
            ),
        )
        raise LoginRateLimitError("credenciais inválidas")

    student_row = conn.execute(
        "SELECT registration, email FROM students WHERE registration = %s",
        (norm_reg,),
    ).fetchone()

    if student_row is not None:
        db_reg = str(student_row["registration"])
        db_email = str(student_row["email"]).strip().lower()
        student_exists = True
    else:
        db_reg = ""
        db_email = ""
        student_exists = False

    reg_ok = _constant_time_equals(norm_reg, db_reg)
    email_ok = _constant_time_equals(norm_email, db_email)
    is_valid = bool(norm_reg and norm_email and student_exists and reg_ok and email_ok)

    if not is_valid:
        conn.execute(
            "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
            (
                f"ip:{norm_ip}",
                "login_failed",
                json.dumps({"ip": norm_ip, "attempted_registration": norm_reg}),
            ),
        )
        raise InvalidCredentialsError("credenciais inválidas")

    issued = create_session(
        conn,
        db_reg,
        ttl_seconds=ttl_seconds,
        actor=f"student:{db_reg}",
    )
    conn.execute(
        "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
        (
            f"student:{db_reg}",
            "login",
            json.dumps({"student_registration": db_reg, "ip": norm_ip}),
        ),
    )
    return issued


def authenticate_session(conn: DictConnection, token: str) -> Session:
    """Validate a raw session token and return the active non-expired Session."""
    if not token or not token.strip():
        raise SessionAuthError("token de sessão ausente")

    token_hash = hash_session_token(token.strip())
    row = conn.execute(
        "SELECT student_registration, created_at, expires_at "
        "FROM sessions "
        "WHERE token_hash = %s AND expires_at > now()",
        (token_hash,),
    ).fetchone()
    if row is None:
        raise SessionAuthError("sessão inválida ou expirada")

    return _row_to_session(row)


def revoke_session(conn: DictConnection, token: str) -> bool:
    """Delete a session by its raw token. Return True if a row was deleted."""
    if not token or not token.strip():
        return False
    token_hash = hash_session_token(token.strip())
    cur = conn.execute(
        "DELETE FROM sessions WHERE token_hash = %s",
        (token_hash,),
    )
    return bool(cur.rowcount and cur.rowcount > 0)


def cleanup_expired_sessions(conn: DictConnection) -> int:
    """Delete all expired sessions and return the number of deleted rows."""
    cur = conn.execute("DELETE FROM sessions WHERE expires_at <= now()")
    return int(cur.rowcount or 0)
