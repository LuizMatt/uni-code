"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# One statement per item. Avoid ':' in SQL (SQLAlchemy treats ':name' as a bind param).
UPGRADE: list[str] = [
    "CREATE EXTENSION IF NOT EXISTS citext",
    """
    CREATE TABLE students (
        registration TEXT PRIMARY KEY
            CHECK (registration <> '' AND registration = btrim(registration)),
        email        CITEXT NOT NULL UNIQUE,
        name         TEXT,
        class_group  TEXT,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE units (
        id        INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        code      TEXT NOT NULL UNIQUE,
        title     TEXT NOT NULL,
        opens_at  TIMESTAMPTZ,
        closes_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE questions (
        id      INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        unit_id INT NOT NULL REFERENCES units (id),
        slug    TEXT NOT NULL UNIQUE,
        title   TEXT NOT NULL,
        active  BOOLEAN NOT NULL DEFAULT TRUE,
        CONSTRAINT uq_questions_id_unit UNIQUE (id, unit_id)
    )
    """,
    """
    CREATE TABLE assignments (
        id                   INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        student_registration TEXT NOT NULL REFERENCES students (registration),
        question_id          INT NOT NULL,
        unit_id              INT NOT NULL REFERENCES units (id),
        round                INT NOT NULL DEFAULT 1 CHECK (round >= 1),
        state                TEXT NOT NULL DEFAULT 'pending'
            CHECK (state IN ('pending', 'passed', 'exhausted', 'replaced')),
        points               NUMERIC(2, 1) NOT NULL DEFAULT 0 CHECK (points IN (0, 0.5)),
        created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT fk_assignments_question_unit
            FOREIGN KEY (question_id, unit_id) REFERENCES questions (id, unit_id),
        CONSTRAINT ck_assignments_points_match_state
            CHECK ((state = 'passed') = (points = 0.5))
    )
    """,
    """
    CREATE UNIQUE INDEX uq_assignments_active
        ON assignments (student_registration, question_id)
        WHERE state <> 'replaced'
    """,
    "CREATE INDEX ix_assignments_student_unit ON assignments (student_registration, unit_id)",
    """
    CREATE TABLE attempts (
        id            INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        assignment_id INT NOT NULL REFERENCES assignments (id),
        number        SMALLINT NOT NULL CHECK (number BETWEEN 1 AND 3),
        status        TEXT NOT NULL DEFAULT 'running'
            CHECK (status IN ('running', 'passed', 'failed', 'error')),
        tests_total   INT CHECK (tests_total >= 0),
        tests_passed  INT CHECK (tests_passed >= 0 AND tests_passed <= tests_total),
        output        TEXT,
        code          TEXT NOT NULL,
        started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        finished_at   TIMESTAMPTZ,
        CONSTRAINT uq_attempts_assignment_number UNIQUE (assignment_id, number)
    )
    """,
    """
    CREATE TABLE sessions (
        token_hash           BYTEA PRIMARY KEY CHECK (octet_length(token_hash) = 32),
        student_registration TEXT NOT NULL REFERENCES students (registration),
        created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
        expires_at           TIMESTAMPTZ NOT NULL,
        CONSTRAINT ck_sessions_expiry CHECK (expires_at > created_at)
    )
    """,
    "CREATE INDEX ix_sessions_expires_at ON sessions (expires_at)",
    """
    CREATE TABLE audit_log (
        id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        actor       TEXT NOT NULL,
        action      TEXT NOT NULL,
        details     JSONB
    )
    """,
    "CREATE INDEX ix_audit_log_occurred_at ON audit_log (occurred_at)",
    """
    CREATE VIEW grades_by_unit AS
    SELECT s.registration, s.email, u.code AS unit, SUM(a.points) AS points
    FROM assignments a
    JOIN students s ON s.registration = a.student_registration
    JOIN units u    ON u.id = a.unit_id
    WHERE a.state <> 'replaced'
    GROUP BY s.registration, s.email, u.code
    """,
]

DOWNGRADE: list[str] = [
    "DROP VIEW grades_by_unit",
    "DROP TABLE audit_log",
    "DROP TABLE sessions",
    "DROP TABLE attempts",
    "DROP TABLE assignments",
    "DROP TABLE questions",
    "DROP TABLE units",
    "DROP TABLE students",
    "DROP EXTENSION IF EXISTS citext",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
