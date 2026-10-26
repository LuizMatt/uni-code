"""grant privileges to unicode_daemon and unicode_panel

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25

The roles are created outside migrations (docker/postgres/init/01-roles-and-databases.sql).
Every new table/view must get explicit grants in its own migration.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE: list[str] = [
    "GRANT USAGE ON SCHEMA public TO unicode_daemon, unicode_panel",
    # daemon: read/write, never deletes history
    "GRANT SELECT, INSERT, UPDATE ON students, units, questions, assignments, attempts "
    "TO unicode_daemon",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON sessions TO unicode_daemon",
    "GRANT SELECT, INSERT ON audit_log TO unicode_daemon",
    "GRANT SELECT ON grades_by_unit TO unicode_daemon",
    "GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO unicode_daemon",
    # panel: read-only, no access to session tokens
    "GRANT SELECT ON students, units, questions, assignments, attempts, audit_log, "
    "grades_by_unit TO unicode_panel",
]

DOWNGRADE: list[str] = [
    "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM unicode_daemon, unicode_panel",
    "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM unicode_daemon, unicode_panel",
    "REVOKE USAGE ON SCHEMA public FROM unicode_daemon, unicode_panel",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
