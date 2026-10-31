"""Persist merchant-only per-turn timing data.

Revision ID: 7e32b4d914c2
Revises: c419a913c101
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "7e32b4d914c2"
down_revision = "c419a913c101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "turn_timings",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("session_id", sa.UUID(), sa.ForeignKey("sessions.session_id"), nullable=False),
        sa.Column("message_id", sa.UUID(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("measurements", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_turn_timings_session_id", "turn_timings", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_turn_timings_session_id", table_name="turn_timings")
    op.drop_table("turn_timings")
