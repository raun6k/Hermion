"""Negotiator-only product fields, merchant escalation/upsell settings, consent state, offer profile.

Revision ID: a5c1d0e7f2b3
Revises: 7e32b4d914c2
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "a5c1d0e7f2b3"
down_revision = "7e32b4d914c2"
branch_labels = None
depends_on = None

PRODUCT_JSON = ("selling_points", "specs", "best_for", "objection_replies", "pairs_with_ids", "upsell_ids")


def upgrade() -> None:
    op.add_column("products", sa.Column("pitch", sa.Text(), nullable=True))
    for name in PRODUCT_JSON:
        op.add_column("products", sa.Column(name, JSONB(), nullable=True))
    op.add_column("merchants", sa.Column("escalation", sa.String(16), nullable=False, server_default="rare"))
    op.add_column(
        "merchants", sa.Column("escalation_gap_pct", sa.Integer(), nullable=False, server_default="5")
    )
    op.add_column(
        "merchants", sa.Column("upsell_enabled", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.add_column("sessions", sa.Column("consent", JSONB(), nullable=True))
    op.add_column("sessions", sa.Column("escalations", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("offers", sa.Column("profile", sa.String(16), nullable=True))
    op.add_column("offers", sa.Column("headroom", sa.String(8), nullable=True))


def downgrade() -> None:
    op.drop_column("offers", "headroom")
    op.drop_column("offers", "profile")
    op.drop_column("sessions", "escalations")
    op.drop_column("sessions", "consent")
    op.drop_column("merchants", "upsell_enabled")
    op.drop_column("merchants", "escalation_gap_pct")
    op.drop_column("merchants", "escalation")
    for name in reversed(PRODUCT_JSON):
        op.drop_column("products", name)
    op.drop_column("products", "pitch")
