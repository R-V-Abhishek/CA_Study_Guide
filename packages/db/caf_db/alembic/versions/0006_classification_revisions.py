"""Forward-only root classification evidence and distinct student verification."""
from alembic import op
import sqlalchemy as sa

revision = "0006_classification_revisions"
down_revision = "0005_extraction_revisions"
branch_labels = None
depends_on = None


def upgrade():
    statements = [
        """CREATE TABLE ingest.suggestion_revision (
          id BIGSERIAL PRIMARY KEY, batch_key TEXT NOT NULL, input_hash TEXT NOT NULL,
          document_id BIGINT NOT NULL REFERENCES ingest.document(id),
          extraction_revision_id BIGINT NOT NULL REFERENCES ingest.extraction_revision(id),
          question_id TEXT NOT NULL, taxonomy_version_id INTEGER NOT NULL REFERENCES ref.taxonomy_version(id),
          run_id BIGINT NOT NULL REFERENCES ops.run(id), experimental BOOLEAN NOT NULL,
          context JSONB NOT NULL, candidates JSONB NOT NULL, mappings JSONB NOT NULL, provenance JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(batch_key,question_id,input_hash))""",
        "CREATE INDEX ix_ingest_suggestion_revision_question_id ON ingest.suggestion_revision(question_id)",
        """CREATE TABLE core.classification_revision (
          id BIGSERIAL PRIMARY KEY, question_id TEXT NOT NULL,
          suggestion_revision_id BIGINT NOT NULL REFERENCES ingest.suggestion_revision(id),
          extraction_revision_id BIGINT NOT NULL REFERENCES ingest.extraction_revision(id),
          taxonomy_version_id INTEGER NOT NULL REFERENCES ref.taxonomy_version(id),
          previous_revision_id BIGINT REFERENCES core.classification_revision(id),
          mappings JSONB NOT NULL, context JSONB NOT NULL, input_hash TEXT NOT NULL,
          actor_id INTEGER NOT NULL REFERENCES app.user_account(id), blind BOOLEAN NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
        "CREATE INDEX ix_core_classification_revision_question_id ON core.classification_revision(question_id)",
        """CREATE TABLE core.question_publication (
          question_id TEXT PRIMARY KEY, document_id BIGINT NOT NULL REFERENCES ingest.document(id),
          current_revision_id BIGINT REFERENCES core.classification_revision(id), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
        """CREATE TABLE core.classification_event (
          id BIGSERIAL PRIMARY KEY, question_id TEXT NOT NULL, revision_id BIGINT REFERENCES core.classification_revision(id),
          actor_id INTEGER NOT NULL REFERENCES app.user_account(id), kind TEXT NOT NULL,
          idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL, payload JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(actor_id,idempotency_key))""",
        """CREATE TABLE core.classification_verification (
          id BIGSERIAL PRIMARY KEY, revision_id BIGINT NOT NULL REFERENCES core.classification_revision(id),
          actor_id INTEGER NOT NULL REFERENCES app.user_account(id), active BOOLEAN NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(revision_id,actor_id))""",
        """CREATE TABLE core.classification_dispute (
          id BIGSERIAL PRIMARY KEY, question_id TEXT NOT NULL,
          revision_id BIGINT NOT NULL REFERENCES core.classification_revision(id),
          proposed_revision_id BIGINT REFERENCES core.classification_revision(id),
          actor_id INTEGER NOT NULL REFERENCES app.user_account(id), reason TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('open','dismissed','replaced')),
          resolved_by INTEGER REFERENCES app.user_account(id), resolution_reason TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
        """CREATE FUNCTION core.reject_classification_history_mutation() RETURNS trigger LANGUAGE plpgsql AS
          $$ BEGIN RAISE EXCEPTION 'Classification history is immutable'; END $$""",
    ]
    for statement in statements:
        op.execute(sa.text(statement))
    for schema, table in (("ingest", "suggestion_revision"), ("core", "classification_revision"), ("core", "classification_event")):
        op.execute(sa.text(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {schema}.{table} FOR EACH ROW EXECUTE FUNCTION core.reject_classification_history_mutation()"))


def downgrade():
    raise RuntimeError("Classification history is retained; restore an audited checkpoint instead")
