"""Add operator-managed trial accounts without changing existing credentials.

Revision ID: 33a1b9c7d204
Revises: 29b6d4a01c75
"""

import sqlalchemy as sa
from alembic import op

revision = "33a1b9c7d204"
down_revision = "29b6d4a01c75"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "trial_accounts",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("journal_id", sa.String(36), sa.ForeignKey("journals.id"), nullable=False),
        sa.Column("operator_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_trial_account_status"),
        sa.CheckConstraint("revision >= 1", name="ck_trial_account_revision"),
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM trial_accounts)")):
        raise RuntimeError("Trial access history exists; refusing to discard suspension state")
    op.drop_table("trial_accounts")
