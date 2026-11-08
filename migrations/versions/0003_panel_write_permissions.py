"""grant panel write permissions for student management

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE: list[str] = [
    "GRANT INSERT, UPDATE, DELETE ON students, assignments, attempts, sessions TO unicode_panel",
    "GRANT INSERT ON audit_log TO unicode_panel",
    "GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO unicode_panel",
]

DOWNGRADE: list[str] = [
    "REVOKE INSERT, UPDATE, DELETE ON students, assignments, attempts, sessions FROM unicode_panel",
    "REVOKE INSERT ON audit_log FROM unicode_panel",
    "REVOKE USAGE ON ALL SEQUENCES IN SCHEMA public TO unicode_panel",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
