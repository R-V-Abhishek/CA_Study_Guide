"""Preserve legacy hierarchy and add immutable, reviewed textbook releases."""
from alembic import op
import sqlalchemy as sa

revision = "0004_textbook_taxonomy"
down_revision = "0003_identity"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    # Frozen DDL: later ORM changes cannot alter this historical migration.
    conn.execute(sa.text("""
    CREATE TABLE ref.taxonomy_release (
        version_id TEXT NOT NULL,
        taxonomy_version_id INTEGER NOT NULL,
        target_attempt TEXT NOT NULL,
        status TEXT NOT NULL,
        manifest_hash TEXT NOT NULL,
        manifest JSONB NOT NULL,
        approved_by INTEGER,
        approved_at TIMESTAMP WITH TIME ZONE,
        approved_review_hash TEXT,
        activated_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (version_id),
        UNIQUE (taxonomy_version_id),
        FOREIGN KEY(taxonomy_version_id) REFERENCES ref.taxonomy_version (id),
        UNIQUE (manifest_hash),
        FOREIGN KEY(approved_by) REFERENCES app.user_account (id)
    )
    """))
    conn.execute(sa.text("""
    CREATE TABLE ref.taxonomy_member (
        taxonomy_version_id INTEGER NOT NULL,
        node_id TEXT NOT NULL,
        paper_id TEXT NOT NULL,
        parent_id TEXT,
        level TEXT NOT NULL,
        name TEXT NOT NULL,
        seq INTEGER NOT NULL,
        heading_origin TEXT NOT NULL,
        PRIMARY KEY (taxonomy_version_id, node_id),
        CONSTRAINT fk_taxonomy_member_parent FOREIGN KEY(taxonomy_version_id, parent_id) REFERENCES ref.taxonomy_member (taxonomy_version_id, node_id) DEFERRABLE INITIALLY DEFERRED,
        FOREIGN KEY(taxonomy_version_id) REFERENCES ref.taxonomy_version (id),
        FOREIGN KEY(node_id) REFERENCES ref.node (id),
        FOREIGN KEY(paper_id) REFERENCES ref.paper (id)
    )
    """))
    conn.execute(sa.text("""
    CREATE TABLE ref.textbook_artifact (
        id TEXT NOT NULL,
        taxonomy_version_id INTEGER NOT NULL,
        paper_id TEXT NOT NULL,
        course_level TEXT NOT NULL,
        edition TEXT NOT NULL,
        availability TEXT NOT NULL,
        sha256 TEXT,
        page_count INTEGER,
        metadata_json JSONB NOT NULL,
        PRIMARY KEY (taxonomy_version_id, id),
        FOREIGN KEY(taxonomy_version_id) REFERENCES ref.taxonomy_version (id)
    )
    """))
    conn.execute(sa.text("""
    CREATE TABLE ref.node_source_span (
        id SERIAL NOT NULL,
        taxonomy_version_id INTEGER NOT NULL,
        node_id TEXT NOT NULL,
        artifact_id TEXT NOT NULL,
        pdf_page_start INTEGER NOT NULL,
        pdf_page_end INTEGER NOT NULL,
        review_status TEXT NOT NULL,
        reviewed_by INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(taxonomy_version_id, node_id) REFERENCES ref.taxonomy_member (taxonomy_version_id, node_id),
        FOREIGN KEY(taxonomy_version_id, artifact_id) REFERENCES ref.textbook_artifact (taxonomy_version_id, id),
        FOREIGN KEY(reviewed_by) REFERENCES app.user_account (id)
    )
    """))
    conn.execute(sa.text("""
    CREATE TABLE ref.descriptor_revision (
        id SERIAL NOT NULL,
        taxonomy_version_id INTEGER NOT NULL,
        node_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        content JSONB NOT NULL,
        content_hash TEXT NOT NULL,
        created_by INTEGER,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (taxonomy_version_id, node_id, revision),
        FOREIGN KEY(taxonomy_version_id, node_id) REFERENCES ref.taxonomy_member (taxonomy_version_id, node_id),
        FOREIGN KEY(created_by) REFERENCES app.user_account (id)
    )
    """))
    conn.execute(sa.text("""
    CREATE TABLE ref.descriptor_approval (
        revision_id INTEGER NOT NULL,
        approved_by INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        approved_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (revision_id),
        FOREIGN KEY(revision_id) REFERENCES ref.descriptor_revision (id),
        FOREIGN KEY(approved_by) REFERENCES app.user_account (id)
    )
    """))
    conn.execute(sa.text("""
    CREATE TABLE ref.taxonomy_crosswalk (
        id SERIAL NOT NULL,
        taxonomy_version_id INTEGER NOT NULL,
        old_node_id TEXT NOT NULL,
        new_node_id TEXT,
        relation TEXT NOT NULL,
        evidence TEXT NOT NULL,
        reviewed_by INTEGER,
        reviewed_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (id),
        FOREIGN KEY(taxonomy_version_id) REFERENCES ref.taxonomy_version (id),
        FOREIGN KEY(old_node_id) REFERENCES ref.node (id),
        FOREIGN KEY(new_node_id) REFERENCES ref.node (id),
        FOREIGN KEY(reviewed_by) REFERENCES app.user_account (id)
    )
    """))
    conn.execute(sa.text("""
    CREATE TABLE app.progress_migration (
        user_id INTEGER NOT NULL,
        crosswalk_id INTEGER NOT NULL,
        migrated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        original_snapshot JSONB NOT NULL,
        PRIMARY KEY (user_id, crosswalk_id),
        FOREIGN KEY(user_id) REFERENCES app.user_account (id),
        FOREIGN KEY(crosswalk_id) REFERENCES ref.taxonomy_crosswalk (id)
    )
    """))
    op.drop_constraint("check_node_level", "node", schema="ref", type_="check")
    op.drop_constraint("check_chapter_parent_null", "node", schema="ref", type_="check")
    op.create_check_constraint("check_node_level", "node", "level IN ('module','chapter','unit','topic','subtopic')", schema="ref")
    op.create_check_constraint("check_chapter_parent_null", "node", "parent_id IS NOT NULL OR level IN ('module','chapter','topic')", schema="ref")
    for schema, table in (("intel", "score_run"), ("ops", "run"), ("ingest", "tag_suggestion")):
        op.add_column(table, sa.Column("taxonomy_version_id", sa.Integer(), sa.ForeignKey("ref.taxonomy_version.id")), schema=schema)
    op.add_column("tag_suggestion", sa.Column("descriptor_revision_id", sa.Integer(), sa.ForeignKey("ref.descriptor_revision.id")), schema="ingest")
    op.add_column("document", sa.Column("course_level", sa.Text()), schema="ingest")
    op.add_column("document", sa.Column("provenance_status", sa.Text(), nullable=False, server_default="unresolved"), schema="ingest")
    op.create_check_constraint("check_document_course_level", "document", "course_level IS NULL OR course_level IN ('foundation','intermediate','final')", schema="ingest")
    op.create_check_constraint("check_document_provenance", "document", "provenance_status IN ('synthetic','unresolved','verified')", schema="ingest")
    op.drop_constraint("check_unit_classify_status", "unit", schema="ingest", type_="check")
    op.create_check_constraint("check_unit_classify_status", "unit", "classify_status IN ('pending','running','suggested','failed','skipped','decided','excluded','needs_review')", schema="ingest")
    # Immutable snapshots are inserted parent-first by service; defer the FK for
    # the baseline bulk snapshot. History and all personal tables remain intact.
    version = conn.scalar(sa.text("INSERT INTO ref.taxonomy_version (yaml_hash,notes) VALUES ('legacy-snapshot-0004','Immutable pre-textbook hierarchy') RETURNING id"))
    conn.execute(sa.text("INSERT INTO ref.taxonomy_member (taxonomy_version_id,node_id,paper_id,parent_id,level,name,seq,heading_origin) SELECT :version,id,paper_id,parent_id,level,name,seq,'legacy' FROM ref.node"), {"version": version})
    conn.execute(sa.text("INSERT INTO ref.taxonomy_release (version_id,taxonomy_version_id,target_attempt,status,manifest_hash,manifest) VALUES ('legacy',:version,'legacy','legacy','legacy-snapshot-0004','{}'::jsonb)"), {"version": version})
    conn.execute(sa.text("""CREATE FUNCTION ref.reject_taxonomy_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Taxonomy history is immutable'; END $$"""))
    for table in ("taxonomy_member", "textbook_artifact", "descriptor_revision", "descriptor_approval", "progress_migration"):
        schema = "app" if table == "progress_migration" else "ref"
        conn.execute(sa.text(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {schema}.{table} FOR EACH ROW EXECUTE FUNCTION ref.reject_taxonomy_history_mutation()"))
    conn.execute(sa.text("CREATE UNIQUE INDEX one_active_taxonomy_release ON ref.taxonomy_release ((status)) WHERE status='active'"))
    conn.execute(sa.text("""CREATE FUNCTION ref.invalidate_release_descriptor_approval() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$ BEGIN UPDATE ref.taxonomy_release SET approved_by=NULL,approved_at=NULL,approved_review_hash=NULL,status=CASE WHEN status='approved' THEN 'draft' ELSE status END WHERE taxonomy_version_id=NEW.taxonomy_version_id; RETURN NEW; END $$"""))
    conn.execute(sa.text("CREATE TRIGGER invalidate_release_on_descriptor AFTER INSERT ON ref.descriptor_revision FOR EACH ROW EXECUTE FUNCTION ref.invalidate_release_descriptor_approval()"))
    for table in ("node_source_span", "taxonomy_crosswalk"):
        conn.execute(sa.text(f"CREATE TRIGGER invalidate_release_on_{table} AFTER INSERT OR UPDATE ON ref.{table} FOR EACH ROW EXECUTE FUNCTION ref.invalidate_release_descriptor_approval()"))
    conn.execute(sa.text("""CREATE FUNCTION ref.protect_taxonomy_release_manifest() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.version_id<>OLD.version_id OR NEW.taxonomy_version_id<>OLD.taxonomy_version_id OR NEW.manifest_hash<>OLD.manifest_hash OR NEW.manifest<>OLD.manifest OR NEW.target_attempt<>OLD.target_attempt THEN RAISE EXCEPTION 'Taxonomy release manifest is immutable'; END IF; RETURN NEW; END $$"""))
    conn.execute(sa.text("CREATE TRIGGER immutable_release_manifest BEFORE UPDATE ON ref.taxonomy_release FOR EACH ROW EXECUTE FUNCTION ref.protect_taxonomy_release_manifest()"))
    conn.execute(sa.text("""CREATE FUNCTION ref.protect_closed_taxonomy_membership() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF EXISTS (SELECT 1 FROM ref.taxonomy_release WHERE taxonomy_version_id=NEW.taxonomy_version_id AND status<>'draft') THEN RAISE EXCEPTION 'Released taxonomy membership is immutable'; END IF; RETURN NEW; END $$"""))
    conn.execute(sa.text("CREATE TRIGGER immutable_closed_membership BEFORE INSERT ON ref.taxonomy_member FOR EACH ROW EXECUTE FUNCTION ref.protect_closed_taxonomy_membership()"))
    conn.execute(sa.text("""CREATE FUNCTION ref.protect_versioned_node() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF EXISTS (SELECT 1 FROM ref.taxonomy_member WHERE node_id=OLD.id) THEN RAISE EXCEPTION 'Versioned taxonomy node is immutable'; END IF; IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF; END $$"""))
    conn.execute(sa.text("CREATE TRIGGER immutable_versioned_node BEFORE UPDATE OR DELETE ON ref.node FOR EACH ROW EXECUTE FUNCTION ref.protect_versioned_node()"))
    for doc_type, answers in (("model_question", False), ("model_answer", True)):
        conn.execute(sa.text("INSERT INTO ref.doc_type (id,signal_class,has_questions,has_answers,description) VALUES (:id,'practice',:questions,:answers,'Official Model Test Paper') ON CONFLICT (id) DO NOTHING"), {"id": doc_type, "questions": not answers, "answers": answers})


def downgrade():
    raise RuntimeError("Textbook taxonomy migration is forward-only; restore a verified checkpoint")
