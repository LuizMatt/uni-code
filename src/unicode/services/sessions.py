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


def hash_session_token(token: str) -> bytes:
    """Return the 32-byte SHA-256 digest of a raw session token."""
    return hashlib.sha256(token.encode("utf-8")).digest()


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
