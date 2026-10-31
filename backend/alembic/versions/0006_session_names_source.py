"""Customer name on sessions and a source tag for seeded history.

Revision ID: b6d2e1a8c4f5
Revises: a5c1d0e7f2b3
"""

import sqlalchemy as sa

from alembic import op

revision = "b6d2e1a8c4f5"
down_revision = "a5c1d0e7f2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("customer_name", sa.String(80), nullable=True))
    op.add_column("sessions", sa.Column("source", sa.String(8), nullable=False, server_default="live"))


def downgrade() -> None:
    op.drop_column("sessions", "source")
    op.drop_column("sessions", "customer_name")
