"""Persist session state transitions.

Revision ID: c419a913c101
Revises: 04b2b6781e42
"""

import sqlalchemy as sa

from alembic import op

revision = "c419a913c101"
down_revision = "04b2b6781e42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "state_changes",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("session_id", sa.UUID(), sa.ForeignKey("sessions.session_id"), nullable=False),
        sa.Column("from_state", sa.String(24), nullable=False),
        sa.Column("to_state", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_state_changes_session_id", "state_changes", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_state_changes_session_id", table_name="state_changes")
    op.drop_table("state_changes")
