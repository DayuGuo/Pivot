"""Private, synthetic editorial workspace state; no canonical workflow migration.

Revision ID: c81b8c41b016
Revises: a99d14733f66
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c81b8c41b016"
down_revision = "a99d14733f66"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "editorial_demo_states",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("journal_id", sa.String(36), sa.ForeignKey("journals.id"), nullable=False),
        sa.Column("case_id", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "journal_id", "case_id"),
    )
    op.create_table(
        "editorial_demo_views",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("journal_id", sa.String(36), sa.ForeignKey("journals.id"), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "journal_id"),
    )


def downgrade():
    op.drop_table("editorial_demo_views")
    op.drop_table("editorial_demo_states")
