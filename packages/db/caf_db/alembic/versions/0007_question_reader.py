"""Phase 6 published reader, reviewed context and durable recomputation evidence."""
from alembic import op
import sqlalchemy as sa

revision = '0007_question_reader'
down_revision = '0006_classification_revisions'
branch_labels = None
depends_on = None


def upgrade():
    statements = [
        """CREATE TABLE core.corpus_generation (
    id INTEGER NOT NULL, 
    generation BIGINT DEFAULT '0' NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (id = 1)
)""",
        """CREATE TABLE core.question_occurrence (
    id BIGSERIAL NOT NULL, 
    canonical_occurrence_id BIGINT REFERENCES core.question_occurrence(id),
    identity_key TEXT NOT NULL, 
    question_id TEXT NOT NULL, 
    paper_id TEXT NOT NULL, 
    attempt_id TEXT, 
    source_family TEXT NOT NULL, 
    signal_class TEXT NOT NULL, 
    series TEXT, 
    identity_status TEXT NOT NULL, 
    pairing_evidence JSONB NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (identity_status IN ('confirmed','ambiguous')), 
    UNIQUE (identity_key), 
    FOREIGN KEY(paper_id) REFERENCES ref.paper (id), 
    FOREIGN KEY(attempt_id) REFERENCES ref.attempt (id)
)""",
        """CREATE TABLE core.published_source (
    id BIGSERIAL NOT NULL, 
    document_id BIGINT NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    title TEXT, 
    doc_type_id TEXT, 
    attempt_id TEXT, 
    page_count INTEGER, 
    approved_blob_path TEXT NOT NULL, 
    official_url TEXT, 
    PRIMARY KEY (id), 
    UNIQUE (sha256)
)""",
        """CREATE TABLE core.published_question (
    id BIGINT NOT NULL, 
    question_id TEXT NOT NULL, 
    extraction_revision_id BIGINT NOT NULL, 
    taxonomy_version_id INTEGER NOT NULL, 
    occurrence_id BIGINT NOT NULL, 
    publication_generation BIGINT NOT NULL, 
    content JSONB NOT NULL, 
    mappings JSONB NOT NULL, 
    covered_subtopics JSONB NOT NULL, 
    marks JSONB NOT NULL, 
    quality JSONB NOT NULL, 
    source_ids JSONB NOT NULL, 
    assets JSONB NOT NULL, 
    search_text TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(id) REFERENCES core.classification_revision (id), 
    FOREIGN KEY(taxonomy_version_id) REFERENCES ref.taxonomy_version (id), 
    FOREIGN KEY(occurrence_id) REFERENCES core.question_occurrence (id)
)""",
        """CREATE INDEX ix_core_published_question_question_id ON core.published_question (question_id)""",
        """CREATE TABLE intel.attempt_taxonomy_binding (
    target_attempt_id TEXT NOT NULL, 
    taxonomy_version_id INTEGER NOT NULL, 
    status TEXT NOT NULL, 
    reviewed_by INTEGER, 
    scoring_config JSONB NOT NULL, 
    PRIMARY KEY (target_attempt_id, taxonomy_version_id), 
    FOREIGN KEY(target_attempt_id) REFERENCES ref.attempt (id), 
    FOREIGN KEY(taxonomy_version_id) REFERENCES ref.taxonomy_version (id), 
    FOREIGN KEY(reviewed_by) REFERENCES app.user_account (id)
)""",
        """CREATE TABLE intel.corpus_coverage (
    taxonomy_version_id INTEGER NOT NULL, 
    paper_id TEXT NOT NULL, 
    attempt_id TEXT NOT NULL, 
    source_family TEXT NOT NULL, 
    inventory_reviewed BOOLEAN NOT NULL, 
    expected_slots INTEGER, 
    discovered_count INTEGER NOT NULL, 
    acquired_count INTEGER NOT NULL, 
    metadata_reviewed BOOLEAN NOT NULL, 
    extraction_reviewed BOOLEAN NOT NULL, 
    pairing_reviewed BOOLEAN NOT NULL, 
    official_scope_confirmed BOOLEAN NOT NULL, 
    gradable_regions_accounted BOOLEAN NOT NULL, 
    labels_complete BOOLEAN NOT NULL, 
    occurrence_resolved BOOLEAN NOT NULL, 
    reviewed_roots INTEGER NOT NULL, 
    reviewed_parts INTEGER NOT NULL, 
    published_roots INTEGER NOT NULL, 
    missing_answers INTEGER NOT NULL, 
    blockers JSONB NOT NULL, 
    PRIMARY KEY (taxonomy_version_id, paper_id, attempt_id, source_family), 
    FOREIGN KEY(taxonomy_version_id) REFERENCES ref.taxonomy_version (id), 
    FOREIGN KEY(paper_id) REFERENCES ref.paper (id), 
    FOREIGN KEY(attempt_id) REFERENCES ref.attempt (id)
)""",
        """CREATE TABLE intel.reviewed_prior (
    taxonomy_version_id INTEGER NOT NULL, 
    node_id TEXT NOT NULL, 
    value FLOAT NOT NULL, 
    source JSONB NOT NULL, 
    reviewed_by INTEGER, 
    PRIMARY KEY (taxonomy_version_id, node_id), 
    CHECK (value >= 0 AND value <= 1), 
    FOREIGN KEY(taxonomy_version_id) REFERENCES ref.taxonomy_version (id), 
    FOREIGN KEY(node_id) REFERENCES ref.node (id), 
    FOREIGN KEY(reviewed_by) REFERENCES app.user_account (id)
)""",
        """CREATE TABLE intel.recompute_job (
    id BIGSERIAL NOT NULL, 
    target_attempt_id TEXT NOT NULL, 
    taxonomy_version_id INTEGER, 
    config_hash TEXT NOT NULL, 
    config_snapshot JSONB NOT NULL, 
    corpus_generation BIGINT NOT NULL, 
    status TEXT NOT NULL, 
    lease_until TIMESTAMP WITH TIME ZONE, 
    lease_token TEXT, 
    attempts INTEGER NOT NULL, 
    last_error TEXT, 
    score_run_id BIGINT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (status IN ('pending','running','ok','failed')), 
    FOREIGN KEY(target_attempt_id) REFERENCES ref.attempt (id), 
    FOREIGN KEY(taxonomy_version_id) REFERENCES ref.taxonomy_version (id), 
    FOREIGN KEY(score_run_id) REFERENCES intel.score_run (id)
)""",
        """CREATE UNIQUE INDEX uq_pending_recompute_context ON intel.recompute_job (target_attempt_id, taxonomy_version_id, config_hash) NULLS NOT DISTINCT WHERE status='pending'""",
        """INSERT INTO core.corpus_generation(id,generation) VALUES (1,0)""",
        """ALTER TABLE core.question_publication ADD COLUMN current_snapshot_id BIGINT REFERENCES core.published_question(id),
          ADD CONSTRAINT check_publication_snapshot_revision CHECK(current_snapshot_id IS NULL OR current_snapshot_id = current_revision_id)""",
        """ALTER TABLE core.appearance ADD COLUMN question_id TEXT, ADD COLUMN part_id TEXT, ADD COLUMN occurrence_id BIGINT REFERENCES core.question_occurrence(id)""",
        """ALTER TABLE intel.score_run ADD COLUMN corpus_generation BIGINT NOT NULL DEFAULT 0, ADD COLUMN input_manifest JSONB NOT NULL DEFAULT '{}', ADD COLUMN stale BOOLEAN NOT NULL DEFAULT false""",
        """DROP INDEX intel.one_current_run""",
        """CREATE UNIQUE INDEX one_current_run ON intel.score_run(target_attempt_id,taxonomy_version_id,config_hash) NULLS NOT DISTINCT WHERE is_current AND NOT shadow""",
        """ALTER TABLE intel.subtopic_score ADD COLUMN evidence JSONB NOT NULL DEFAULT '{}'""",
        """ALTER TABLE intel.subtopic_score ALTER COLUMN exam_score DROP NOT NULL""",
        """ALTER TABLE intel.subtopic_score ALTER COLUMN practice_score DROP NOT NULL""",
        """ALTER TABLE intel.subtopic_score ALTER COLUMN weight_prior DROP NOT NULL""",
        """ALTER TABLE intel.subtopic_score ALTER COLUMN importance DROP NOT NULL""",
        """CREATE INDEX ix_published_question_fts ON core.published_question USING GIN (to_tsvector('english',search_text))""",
        """CREATE TRIGGER immutable_published_source BEFORE UPDATE OR DELETE ON core.published_source FOR EACH ROW EXECUTE FUNCTION core.reject_classification_history_mutation()""",
        """CREATE TRIGGER immutable_published_question BEFORE UPDATE OR DELETE ON core.published_question FOR EACH ROW EXECUTE FUNCTION core.reject_classification_history_mutation()""",
        """CREATE FUNCTION core.enqueue_corpus_generation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO intel.recompute_job(target_attempt_id,taxonomy_version_id,config_hash,config_snapshot,corpus_generation,status,attempts)
 SELECT target_attempt_id,taxonomy_version_id,config_hash,config_snapshot,NEW.generation,'pending',0
 FROM (SELECT DISTINCT ON (target_attempt_id,taxonomy_version_id,config_hash)
 target_attempt_id,taxonomy_version_id,config_hash,config_snapshot FROM (
 SELECT target_attempt_id,taxonomy_version_id,config_hash,config_snapshot,id AS precedence FROM intel.score_run WHERE status='ok' AND NOT shadow AND config_snapshot IS NOT NULL
 UNION ALL SELECT target_attempt_id,taxonomy_version_id,config_hash,config_snapshot,id AS precedence FROM intel.recompute_job WHERE status IN ('pending','running')
 ) contexts ORDER BY target_attempt_id,taxonomy_version_id,config_hash,precedence DESC) selected
 WHERE (selected.taxonomy_version_id IS NULL AND NOT EXISTS (
   SELECT 1 FROM ref.taxonomy_release WHERE status<>'legacy'
 )) OR EXISTS (
   SELECT 1 FROM intel.attempt_taxonomy_binding binding
   JOIN ref.taxonomy_release release ON release.taxonomy_version_id=binding.taxonomy_version_id
   WHERE binding.target_attempt_id=selected.target_attempt_id
     AND binding.taxonomy_version_id=selected.taxonomy_version_id
     AND binding.status='reviewed' AND binding.reviewed_by IS NOT NULL
     AND release.status IN ('approved','active','archived') AND release.approved_by IS NOT NULL
 )
 ON CONFLICT (target_attempt_id,taxonomy_version_id,config_hash) WHERE status='pending'
 DO UPDATE SET corpus_generation=GREATEST(intel.recompute_job.corpus_generation,EXCLUDED.corpus_generation);
 RETURN NEW;
END $$""",
        """CREATE TRIGGER enqueue_generation AFTER UPDATE OF generation ON core.corpus_generation FOR EACH ROW WHEN (OLD.generation IS DISTINCT FROM NEW.generation) EXECUTE FUNCTION core.enqueue_corpus_generation()""",
        """CREATE FUNCTION core.invalidate_corpus() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP = 'UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN RETURN NULL; END IF;
 UPDATE core.corpus_generation SET generation=generation+1 WHERE id=1;
 RETURN NULL;
END $$""",
        """CREATE TRIGGER invalidate_corpus_coverage AFTER INSERT OR UPDATE OR DELETE ON intel.corpus_coverage FOR EACH ROW EXECUTE FUNCTION core.invalidate_corpus()""",
        """CREATE TRIGGER invalidate_attempt_taxonomy_binding AFTER INSERT OR UPDATE OR DELETE ON intel.attempt_taxonomy_binding FOR EACH ROW EXECUTE FUNCTION core.invalidate_corpus()""",
        """CREATE TRIGGER invalidate_reviewed_prior AFTER INSERT OR UPDATE OR DELETE ON intel.reviewed_prior FOR EACH ROW EXECUTE FUNCTION core.invalidate_corpus()""",
        """CREATE TRIGGER invalidate_question_occurrence AFTER INSERT OR UPDATE OR DELETE ON core.question_occurrence FOR EACH ROW EXECUTE FUNCTION core.invalidate_corpus()""",
        """CREATE TRIGGER invalidate_applicability_rule AFTER INSERT OR UPDATE OR DELETE ON ref.applicability_rule FOR EACH ROW EXECUTE FUNCTION core.invalidate_corpus()""",
        """CREATE FUNCTION core.reconcile_reviewed_pairs() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  UPDATE core.question_occurrence answer SET canonical_occurrence_id=paper.id,
    identity_status='confirmed', pairing_evidence=answer.pairing_evidence ||
      jsonb_build_object('reconciled_pair_id',pair.id,'confirmed_pair_evidence',pair.evidence)
  FROM ingest.document_pair pair, core.question_occurrence paper
  WHERE pair.status='confirmed' AND pair.confirmed_by IS NOT NULL
    AND answer.pairing_evidence->>'canonical_document_id'=pair.answer_document_id::text
    AND paper.pairing_evidence->>'canonical_document_id'=pair.question_document_id::text
    AND answer.paper_id=paper.paper_id
    AND answer.attempt_id IS NOT DISTINCT FROM paper.attempt_id
    AND answer.series IS NOT DISTINCT FROM paper.series
    AND answer.pairing_evidence->>'question_label'=paper.pairing_evidence->>'question_label'
    AND answer.id<>paper.id AND paper.canonical_occurrence_id IS NULL
    AND answer.canonical_occurrence_id IS DISTINCT FROM paper.id;
  UPDATE core.question_occurrence answer SET canonical_occurrence_id=NULL,identity_status='ambiguous'
  WHERE answer.canonical_occurrence_id IS NOT NULL AND
    NOT EXISTS (SELECT 1 FROM ingest.document_pair pair
      WHERE pair.id::text=answer.pairing_evidence->>'reconciled_pair_id' AND pair.status='confirmed');
  RETURN NULL;
END $$""",
        """CREATE TRIGGER reconcile_document_pair AFTER INSERT OR UPDATE OR DELETE ON ingest.document_pair
          FOR EACH STATEMENT EXECUTE FUNCTION core.reconcile_reviewed_pairs()""",
        """CREATE TRIGGER reconcile_new_occurrence AFTER INSERT ON core.question_occurrence
          FOR EACH STATEMENT EXECUTE FUNCTION core.reconcile_reviewed_pairs()""",
        """CREATE TRIGGER invalidate_document_pair AFTER INSERT OR UPDATE OR DELETE ON ingest.document_pair
          FOR EACH ROW EXECUTE FUNCTION core.invalidate_corpus()""",
        """CREATE FUNCTION core.invalidate_publication_pointer() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.current_snapshot_id IS NOT DISTINCT FROM NEW.current_snapshot_id THEN RETURN NEW; END IF;
 IF NEW.current_snapshot_id IS NULL OR NOT EXISTS (
   SELECT 1 FROM core.published_question q, core.corpus_generation g
   WHERE q.id=NEW.current_snapshot_id AND g.id=1 AND q.publication_generation=g.generation
 ) THEN UPDATE core.corpus_generation SET generation=generation+1 WHERE id=1; END IF;
 RETURN NEW;
END $$""",
        """CREATE TRIGGER invalidate_publication_pointer AFTER UPDATE OF current_snapshot_id ON core.question_publication
          FOR EACH ROW EXECUTE FUNCTION core.invalidate_publication_pointer()""",
    ]
    for statement in statements:
        op.execute(sa.text(statement))


def downgrade():
    raise RuntimeError('Published evidence and study history are retained; restore an audited checkpoint instead')
