"""Explicit session identity with multiple pre-granted roles in one journal.

Revision ID: 29b6d4a01c75
Revises: 28a7c1e09462
"""

import sqlalchemy as sa
from alembic import op

revision = "29b6d4a01c75"
down_revision = "28a7c1e09462"
branch_labels = None
depends_on = None


def upgrade():
    # Preserve every existing row and bind only provably unambiguous old sessions.
    op.drop_constraint("memberships_user_id_journal_id_key", "memberships", type_="unique")
    op.create_unique_constraint(
        "uq_membership_user_journal_role", "memberships", ["user_id", "journal_id", "role"]
    )
    op.create_unique_constraint("uq_membership_id_user", "memberships", ["id", "user_id"])
    op.add_column("login_sessions", sa.Column("active_membership_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_session_active_membership_user",
        "login_sessions",
        "memberships",
        ["active_membership_id", "user_id"],
        ["id", "user_id"],
    )
    op.execute("""
        UPDATE login_sessions s SET active_membership_id=m.id FROM memberships m
        WHERE m.user_id=s.user_id AND
        (SELECT count(*) FROM memberships x WHERE x.user_id=s.user_id)=1
    """)


def downgrade():
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM memberships GROUP BY user_id,journal_id HAVING count(*)>1)"
        )
    ):
        raise RuntimeError(
            "Cannot downgrade while multiple roles exist; grants must not be discarded"
        )
    op.drop_constraint("fk_session_active_membership_user", "login_sessions", type_="foreignkey")
    op.drop_column("login_sessions", "active_membership_id")
    op.drop_constraint("uq_membership_id_user", "memberships", type_="unique")
    op.drop_constraint("uq_membership_user_journal_role", "memberships", type_="unique")
    op.create_unique_constraint(
        "memberships_user_id_journal_id_key", "memberships", ["user_id", "journal_id"]
    )
