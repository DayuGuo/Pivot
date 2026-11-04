"""Append-only per-claim human feedback; preserves every existing answer and approval."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "16c40fda8397"
down_revision = "15b39ecf7286"
branch_labels = None
depends_on = None
GUARDS = """
CREATE FUNCTION publishing_claim_review_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE a publishing_dossier_answers; v publishing_dossier_versions; owner_id text; previous_no integer;
BEGIN
 SELECT * INTO a FROM publishing_dossier_answers WHERE id=NEW.answer_id;
 SELECT * INTO v FROM publishing_dossier_versions WHERE id=NEW.version_id;
 SELECT created_by INTO owner_id FROM publishing_dossiers WHERE id=NEW.dossier_id FOR UPDATE;
 IF a.id IS NULL OR v.id IS NULL OR a.dossier_id IS DISTINCT FROM NEW.dossier_id OR a.journal_id IS DISTINCT FROM NEW.journal_id
    OR a.version_id IS DISTINCT FROM NEW.version_id OR NEW.content_digest IS DISTINCT FROM v.content_digest
    OR NEW.reviewed_by IS DISTINCT FROM owner_id
    OR (a.result_json -> NEW.claim_bucket -> NEW.claim_index) IS NULL
    OR NEW.claim_json IS DISTINCT FROM (a.result_json -> NEW.claim_bucket -> NEW.claim_index) THEN
   RAISE EXCEPTION 'Invalid claim review source' USING ERRCODE='23514';
 END IF;
 SELECT coalesce(max(review_no),0) INTO previous_no FROM publishing_claim_reviews
 WHERE answer_id=NEW.answer_id AND claim_bucket=NEW.claim_bucket AND claim_index=NEW.claim_index;
 IF NEW.review_no<>previous_no+1 THEN
   RAISE EXCEPTION 'Invalid claim review sequence' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER claim_review_insert BEFORE INSERT ON publishing_claim_reviews FOR EACH ROW EXECUTE FUNCTION publishing_claim_review_guard();
CREATE TRIGGER claim_review_immutable BEFORE UPDATE OR DELETE ON publishing_claim_reviews FOR EACH ROW EXECUTE FUNCTION publishing_dossier_immutable();
CREATE TRIGGER claim_review_truncate BEFORE TRUNCATE ON publishing_claim_reviews FOR EACH STATEMENT EXECUTE FUNCTION publishing_dossier_immutable();
"""


def upgrade():
    op.create_table(
        "publishing_claim_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "answer_id",
            sa.String(36),
            sa.ForeignKey("publishing_dossier_answers.id"),
            nullable=False,
        ),
        sa.Column("dossier_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("claim_bucket", sa.String(20), nullable=False),
        sa.Column("claim_index", sa.Integer(), nullable=False),
        sa.Column("claim_json", postgresql.JSONB(), nullable=False),
        sa.Column("claim_digest", sa.String(64), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("verdict", sa.String(20), nullable=False),
        sa.Column("note", sa.String(2000), nullable=False),
        sa.Column("review_no", sa.Integer(), nullable=False),
        sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_claim_review_version",
        ),
        sa.UniqueConstraint(
            "answer_id", "claim_bucket", "claim_index", "review_no", name="uq_claim_review_sequence"
        ),
        sa.CheckConstraint(
            "claim_bucket IN ('claims','withheld_claims') AND claim_index BETWEEN 0 AND 5 AND review_no>=1",
            name="ck_claim_review_target",
        ),
        sa.CheckConstraint(
            "verdict IN ('supported','unsupported','uncertain') AND length(btrim(note)) BETWEEN 5 AND 2000",
            name="ck_claim_review_verdict",
        ),
        sa.CheckConstraint(
            "claim_digest ~ '^[0-9a-f]{64}$' AND content_digest ~ '^[0-9a-f]{64}$' AND session_hash ~ '^[0-9a-f]{64}$'",
            name="ck_claim_review_hashes",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(claim_json)='object' AND octet_length(claim_json::text)<=32768",
            name="ck_claim_review_snapshot",
        ),
    )
    op.execute(GUARDS)


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM publishing_claim_reviews)")):
        raise RuntimeError("Refusing to remove human claim review history")
    op.drop_table("publishing_claim_reviews")
    op.execute("DROP FUNCTION publishing_claim_review_guard()")
