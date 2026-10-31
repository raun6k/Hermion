"""A pending shopkeeper price check on the session; a pending voice-setup style proposal on the shop.

Revision ID: c7e3f2b9d1a6
Revises: b6d2e1a8c4f5
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "c7e3f2b9d1a6"
down_revision = "b6d2e1a8c4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("pending_check", JSONB(), nullable=True))
    op.add_column("merchants", sa.Column("pending_style", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("merchants", "pending_style")
    op.drop_column("sessions", "pending_check")
