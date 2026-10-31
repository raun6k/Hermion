"""Persist tool calls in the merchant trace.

Revision ID: 04b2b6781e42
Revises: d3faa88dff10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "04b2b6781e42"
down_revision = "d3faa88dff10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("session_id", sa.UUID(), sa.ForeignKey("sessions.session_id"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("arguments", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_tool_calls_session_id", "tool_calls", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_tool_calls_session_id", table_name="tool_calls")
    op.drop_table("tool_calls")
