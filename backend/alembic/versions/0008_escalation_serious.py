"""Default escalation becomes `serious`: the shopkeeper is asked about any below-floor offer from a
customer who is not lowballing.

Revision ID: d8f4a3c0e2b7
Revises: c7e3f2b9d1a6
"""

from alembic import op

revision = "d8f4a3c0e2b7"
down_revision = "c7e3f2b9d1a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("merchants", "escalation", server_default="serious")
    op.execute("UPDATE merchants SET escalation = 'serious' WHERE escalation = 'rare'")


def downgrade() -> None:
    op.execute("UPDATE merchants SET escalation = 'rare' WHERE escalation = 'serious'")
    op.alter_column("merchants", "escalation", server_default="rare")
