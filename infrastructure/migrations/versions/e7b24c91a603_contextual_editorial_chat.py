"""Private persistent contextual Mock turns; no formal workflow changes.

Revision ID: e7b24c91a603
Revises: c81b8c41b016
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e7b24c91a603"
down_revision = "c81b8c41b016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "editorial_chat_turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("journal_id", sa.String(36), sa.ForeignKey("journals.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "journal_id", "request_id"),
    )
    op.create_index(
        "ix_editorial_chat_history",
        "editorial_chat_turns",
        ["user_id", "journal_id", "created_at", "id"],
    )


def downgrade():
    op.drop_index("ix_editorial_chat_history", table_name="editorial_chat_turns")
    op.drop_table("editorial_chat_turns")
