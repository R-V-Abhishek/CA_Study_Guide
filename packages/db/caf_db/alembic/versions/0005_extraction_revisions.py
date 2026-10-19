"""Forward-only extraction history; legacy units and publications remain intact."""
from alembic import op
import sqlalchemy as sa

revision = "0005_extraction_revisions"
down_revision = "0004_textbook_taxonomy"
branch_labels = None
depends_on = None


def upgrade():
    # Frozen DDL independent of future ORM changes.
    statements = [
        """CREATE TABLE ingest.extraction_revision (
            id BIGSERIAL PRIMARY KEY, document_id BIGINT NOT NULL REFERENCES ingest.document(id),
            run_id BIGINT NOT NULL REFERENCES ops.run(id), base_revision_id BIGINT REFERENCES ingest.extraction_revision(id),
            status TEXT NOT NULL CHECK(status IN ('candidate','current','superseded','failed')),
            content_digest VARCHAR(64) NOT NULL, profile_id TEXT NOT NULL,
            configuration JSONB NOT NULL, quality JSONB NOT NULL, questions JSONB NOT NULL, parsed_units JSONB NOT NULL,
            created_by INTEGER REFERENCES app.user_account(id), created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            promoted_at TIMESTAMPTZ, CONSTRAINT uq_extraction_content UNIQUE(document_id,content_digest))""",
        """CREATE TABLE ingest.content_block (
            id BIGSERIAL PRIMARY KEY, revision_id BIGINT NOT NULL REFERENCES ingest.extraction_revision(id),
            block_key TEXT NOT NULL, sequence INTEGER NOT NULL, page INTEGER NOT NULL,
            bbox JSONB NOT NULL, raw_text TEXT NOT NULL, normalized_text TEXT NOT NULL, origin TEXT NOT NULL,
            UNIQUE(revision_id,block_key))""",
        """CREATE TABLE ingest.extraction_asset (
            id BIGSERIAL PRIMARY KEY, revision_id BIGINT NOT NULL REFERENCES ingest.extraction_revision(id),
            page INTEGER NOT NULL, kind TEXT NOT NULL, bbox JSONB, concerns JSONB NOT NULL)""",
        """CREATE TABLE ingest.document_pair (
            id BIGSERIAL PRIMARY KEY, question_document_id BIGINT NOT NULL REFERENCES ingest.document(id),
            answer_document_id BIGINT NOT NULL REFERENCES ingest.document(id), status TEXT NOT NULL,
            evidence JSONB NOT NULL, confirmed_by INTEGER REFERENCES app.user_account(id), confirmed_at TIMESTAMPTZ,
            UNIQUE(question_document_id,answer_document_id))""",
        """CREATE TABLE ingest.extraction_review (
            id BIGSERIAL PRIMARY KEY, revision_id BIGINT NOT NULL REFERENCES ingest.extraction_revision(id),
            actor_id INTEGER NOT NULL REFERENCES app.user_account(id), content_digest VARCHAR(64) NOT NULL,
            dimension TEXT NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
        """CREATE TABLE ingest.reconciliation_link (
            id BIGSERIAL PRIMARY KEY, revision_id BIGINT NOT NULL REFERENCES ingest.extraction_revision(id),
            old_unit_id BIGINT REFERENCES ingest.unit(id), new_label TEXT, relation TEXT NOT NULL, evidence JSONB NOT NULL)""",
        "ALTER TABLE ingest.document ADD COLUMN collection_id TEXT",
        "ALTER TABLE ingest.document ADD COLUMN paper_page_ranges JSONB NOT NULL DEFAULT '[]'",
        "ALTER TABLE ingest.document ADD COLUMN metadata_evidence JSONB NOT NULL DEFAULT '{}'",
        "ALTER TABLE ingest.document ADD COLUMN current_revision_id BIGINT REFERENCES ingest.extraction_revision(id)",
        "ALTER TABLE ingest.unit ADD COLUMN revision_id BIGINT REFERENCES ingest.extraction_revision(id)",
        "ALTER TABLE ingest.unit ADD COLUMN content_digest VARCHAR(64)",
        "ALTER TABLE ingest.unit ADD COLUMN stable_question_id TEXT",
        "ALTER TABLE ingest.unit ADD COLUMN extraction_data JSONB NOT NULL DEFAULT '{}'",
        "CREATE UNIQUE INDEX uq_current_extraction_revision ON ingest.extraction_revision(document_id) WHERE status='current'",
        "CREATE INDEX ix_unit_revision ON ingest.unit(revision_id)",
        "ALTER TABLE ingest.unit DROP CONSTRAINT uq_unit_doc_run_label",
        "CREATE UNIQUE INDEX uq_unit_legacy_doc_run_label ON ingest.unit(document_id,extract_run_id,label_path) WHERE revision_id IS NULL",
        "CREATE UNIQUE INDEX uq_unit_revision_label ON ingest.unit(revision_id,label_path) WHERE revision_id IS NOT NULL",
    ]
    for statement in statements:
        op.execute(sa.text(statement))


def downgrade():
    raise RuntimeError("Extraction revisions retain review/publication history; restore an audited checkpoint instead")
