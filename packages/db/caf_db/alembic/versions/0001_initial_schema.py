"""Frozen initial schema for CAF.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-24 20:52:00.000000

This revision deliberately does not import application models. All subsequent
schema changes require an explicit forward migration.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    for schema in ("ops", "ref", "ingest", "core", "intel", "app"):
        op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    op.create_table(
        'user_account',
        sa.Column('id', sa.SmallInteger(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='app',
    )
    op.create_table(
        'change_log',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('entity', sa.Text(), nullable=False),
        sa.Column('entity_id', sa.Text(), nullable=False),
        sa.Column('change', sa.Text(), nullable=False),
        sa.Column('before', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='core',
    )
    op.create_table(
        'decision',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('unit_fingerprint', sa.String(length=40), nullable=False),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('suggestion_run_id', sa.BigInteger(), nullable=True),
        sa.Column('blind', sa.Boolean(), nullable=False),
        sa.Column('seconds_spent', sa.Float(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("action IN ('accept','accept_alt','edit','none_fits','exclude','bulk_accept','undo')", name='check_decision_action'),
        sa.PrimaryKeyConstraint('id'),
        schema='core',
    )
    op.create_index('ix_core_decision_fingerprint_date', 'decision', ['unit_fingerprint', 'decided_at'], unique=False, schema='core')
    op.create_table(
        'source_page',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('source_id', sa.Text(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('depth', sa.Integer(), nullable=False),
        sa.Column('parent_page_id', sa.BigInteger(), nullable=True),
        sa.Column('fetch_mode', sa.Text(), nullable=False),
        sa.Column('robots_allowed', sa.Boolean(), nullable=True),
        sa.Column('last_fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('etag', sa.Text(), nullable=True),
        sa.Column('last_modified', sa.Text(), nullable=True),
        sa.Column('link_count', sa.Integer(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.CheckConstraint("fetch_mode IN ('http','browser','assisted')", name='check_source_page_fetch_mode'),
        sa.ForeignKeyConstraint(['parent_page_id'], ['ingest.source_page.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url'),
        schema='ingest',
    )
    op.create_table(
        'run',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('stage', sa.Text(), nullable=False),
        sa.Column('git_sha', sa.Text(), nullable=True),
        sa.Column('config_hash', sa.Text(), nullable=True),
        sa.Column('args', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('stats', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('running','ok','partial','failed','aborted_budget')", name='check_run_status'),
        sa.PrimaryKeyConstraint('id'),
        schema='ops',
    )
    op.create_table(
        'attempt',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('exam_year', sa.Integer(), nullable=False),
        sa.Column('exam_month', sa.Integer(), nullable=False),
        sa.Column('label', sa.Text(), nullable=False),
        sa.Column('exam_start_date', sa.Date(), nullable=True),
        sa.Column('verified', sa.Boolean(), nullable=False),
        sa.CheckConstraint('exam_month BETWEEN 1 AND 12', name='check_exam_month'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('exam_year', 'exam_month', name='uq_attempt_year_month'),
        schema='ref',
    )
    op.create_table(
        'doc_type',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('signal_class', sa.Text(), nullable=False),
        sa.Column('has_questions', sa.Boolean(), nullable=False),
        sa.Column('has_answers', sa.Boolean(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.CheckConstraint("signal_class IN ('exam','practice','reference')", name='check_doc_type_signal_class'),
        sa.PrimaryKeyConstraint('id'),
        schema='ref',
    )
    op.create_table(
        'instrument',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('paper_codes', sa.ARRAY(sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='ref',
    )
    op.create_table(
        'scheme',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='ref',
    )
    op.create_table(
        'taxonomy_version',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('git_sha', sa.Text(), nullable=True),
        sa.Column('yaml_hash', sa.Text(), nullable=False),
        sa.Column('loaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='ref',
    )
    op.create_table(
        'settings',
        sa.Column('user_id', sa.SmallInteger(), nullable=False),
        sa.Column('target_attempt_id', sa.Text(), nullable=True),
        sa.Column('exam_start_date', sa.Date(), nullable=True),
        sa.Column('hours_per_week', sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column('minutes_per_subtopic', sa.Integer(), nullable=False),
        sa.Column('revision_intervals', sa.ARRAY(sa.Integer()), nullable=False),
        sa.ForeignKeyConstraint(['target_attempt_id'], ['ref.attempt.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['app.user_account.id'], ),
        sa.PrimaryKeyConstraint('user_id'),
        schema='app',
    )
    op.create_table(
        'score_run',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('scoring_version', sa.Text(), nullable=False),
        sa.Column('config_hash', sa.Text(), nullable=False),
        sa.Column('target_attempt_id', sa.Text(), nullable=False),
        sa.Column('shadow', sa.Boolean(), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('running','ok','failed')", name='check_score_run_status'),
        sa.ForeignKeyConstraint(['target_attempt_id'], ['ref.attempt.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='intel',
    )
    op.create_index('one_current_run', 'score_run', ['is_current'], unique=True, schema='intel', postgresql_where=sa.text('is_current AND NOT shadow'))
    op.create_table(
        'event',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.BigInteger(), nullable=True),
        sa.Column('level', sa.Text(), nullable=False),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("level IN ('info','warn','error','alarm')", name='check_event_level'),
        sa.ForeignKeyConstraint(['run_id'], ['ops.run.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='ops',
    )
    op.create_table(
        'llm_call',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.BigInteger(), nullable=False),
        sa.Column('task', sa.Text(), nullable=False),
        sa.Column('model_id', sa.Text(), nullable=False),
        sa.Column('prompt_version', sa.Text(), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('cached_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(precision=10, scale=5), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('batch_job_id', sa.Text(), nullable=True),
        sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('ok','retry','schema_error','error')", name='check_llm_call_status'),
        sa.ForeignKeyConstraint(['run_id'], ['ops.run.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='ops',
    )
    op.create_table(
        'law_boundary',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('paper_code', sa.Text(), nullable=False),
        sa.Column('instrument_id', sa.Text(), nullable=True),
        sa.Column('first_applicable_attempt', sa.Text(), nullable=True),
        sa.Column('scope_node_ids', sa.ARRAY(sa.Text()), nullable=True),
        sa.Column('policy', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.CheckConstraint("policy IN ('mark_stale','exclude')", name='check_law_boundary_policy'),
        sa.ForeignKeyConstraint(['first_applicable_attempt'], ['ref.attempt.id'], ),
        sa.ForeignKeyConstraint(['instrument_id'], ['ref.instrument.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='ref',
    )
    op.create_table(
        'paper',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('scheme_id', sa.Text(), nullable=False),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('group_no', sa.Integer(), nullable=True),
        sa.Column('max_marks', sa.Integer(), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['scheme_id'], ['ref.scheme.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scheme_id', 'code', name='uq_paper_scheme_code'),
        schema='ref',
    )
    op.create_table(
        'mock_test',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.SmallInteger(), nullable=False),
        sa.Column('paper_id', sa.Text(), nullable=False),
        sa.Column('attempt_id', sa.Text(), nullable=True),
        sa.Column('label', sa.Text(), nullable=True),
        sa.Column('score', sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column('max_score', sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column('taken_on', sa.Date(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.CheckConstraint('max_score > 0', name='check_mock_test_max_score'),
        sa.ForeignKeyConstraint(['attempt_id'], ['ref.attempt.id'], ),
        sa.ForeignKeyConstraint(['paper_id'], ['ref.paper.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='app',
    )
    op.create_table(
        'appearance',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('unit_fingerprint', sa.String(length=40), nullable=False),
        sa.Column('source_unit_id', sa.BigInteger(), nullable=True),
        sa.Column('doc_sha256', sa.String(length=64), nullable=False),
        sa.Column('attempt_id', sa.Text(), nullable=False),
        sa.Column('source_paper_id', sa.Text(), nullable=False),
        sa.Column('doc_type_id', sa.Text(), nullable=False),
        sa.Column('signal_class', sa.Text(), nullable=False),
        sa.Column('series', sa.Text(), nullable=True),
        sa.Column('display_label', sa.Text(), nullable=False),
        sa.Column('marks', sa.Integer(), nullable=True),
        sa.Column('gist', sa.Text(), nullable=False),
        sa.Column('official_url', sa.Text(), nullable=True),
        sa.Column('official_url_dead', sa.Boolean(), nullable=False),
        sa.Column('page_start', sa.Integer(), nullable=False),
        sa.Column('page_end', sa.Integer(), nullable=False),
        sa.Column('law_stale', sa.Boolean(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('duplicate_of', sa.BigInteger(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("signal_class IN ('exam','practice')", name='check_appearance_signal_class'),
        sa.CheckConstraint("status IN ('published','orphaned','withdrawn')", name='check_appearance_status'),
        sa.ForeignKeyConstraint(['attempt_id'], ['ref.attempt.id'], ),
        sa.ForeignKeyConstraint(['doc_type_id'], ['ref.doc_type.id'], ),
        sa.ForeignKeyConstraint(['duplicate_of'], ['core.appearance.id'], ),
        sa.ForeignKeyConstraint(['source_paper_id'], ['ref.paper.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('unit_fingerprint'),
        schema='core',
    )
    op.create_index('ix_core_appearance_attempt_signal', 'appearance', ['attempt_id', 'signal_class'], unique=False, schema='core', postgresql_where=sa.text("status = 'published'"))
    op.create_table(
        'depth_gate_report',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('paper_code', sa.Text(), nullable=False),
        sa.Column('band', sa.Text(), nullable=False),
        sa.Column('baseline_run_id', sa.BigInteger(), nullable=True),
        sa.Column('shadow_run_id', sa.BigInteger(), nullable=True),
        sa.Column('top_k', sa.Integer(), nullable=False),
        sa.Column('jaccard', sa.Float(), nullable=True),
        sa.Column('spearman', sa.Float(), nullable=True),
        sa.Column('newly_asked_nodes', sa.Integer(), nullable=True),
        sa.Column('units_to_review', sa.Integer(), nullable=True),
        sa.Column('est_review_hours', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('decision', sa.Text(), nullable=True),
        sa.Column('decided_note', sa.Text(), nullable=True),
        sa.CheckConstraint("decision IN ('continue','continue_practice_value','stop')", name='check_depth_gate_decision'),
        sa.ForeignKeyConstraint(['baseline_run_id'], ['intel.score_run.id'], ),
        sa.ForeignKeyConstraint(['shadow_run_id'], ['intel.score_run.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='intel',
    )
    op.create_table(
        'ingestion_coverage',
        sa.Column('score_run_id', sa.BigInteger(), nullable=False),
        sa.Column('paper_id', sa.Text(), nullable=False),
        sa.Column('attempt_id', sa.Text(), nullable=False),
        sa.Column('exam_published', sa.Boolean(), nullable=False),
        sa.Column('practice_published', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['score_run_id'], ['intel.score_run.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('score_run_id', 'paper_id', 'attempt_id'),
        schema='intel',
    )
    op.create_table(
        'node',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('paper_id', sa.Text(), nullable=False),
        sa.Column('parent_id', sa.Text(), nullable=True),
        sa.Column('level', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('sm_ref', sa.Text(), nullable=True),
        sa.Column('sm_pages', postgresql.INT4RANGE(), nullable=True),
        sa.Column('created_in', sa.Integer(), nullable=True),
        sa.Column('updated_in', sa.Integer(), nullable=True),
        sa.CheckConstraint("((level = 'chapter') = (parent_id IS NULL))", name='check_chapter_parent_null'),
        sa.CheckConstraint("level IN ('chapter','topic','subtopic')", name='check_node_level'),
        sa.CheckConstraint("status IN ('active','deprecated')", name='check_node_status'),
        sa.ForeignKeyConstraint(['created_in'], ['ref.taxonomy_version.id'], ),
        sa.ForeignKeyConstraint(['paper_id'], ['ref.paper.id'], ),
        sa.ForeignKeyConstraint(['parent_id'], ['ref.node.id'], ),
        sa.ForeignKeyConstraint(['updated_in'], ['ref.taxonomy_version.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='ref',
    )
    op.create_index('ix_ref_node_paper_id_level', 'node', ['paper_id', 'level'], unique=False, schema='ref')
    op.create_index('ix_ref_node_parent_id', 'node', ['parent_id'], unique=False, schema='ref')
    op.create_table(
        'weightage_section',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('paper_id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('min_pct', sa.Numeric(), nullable=False),
        sa.Column('max_pct', sa.Numeric(), nullable=False),
        sa.Column('valid_from_attempt', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['paper_id'], ['ref.paper.id'], ),
        sa.ForeignKeyConstraint(['valid_from_attempt'], ['ref.attempt.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='ref',
    )
    op.create_table(
        'note',
        sa.Column('user_id', sa.SmallInteger(), nullable=False),
        sa.Column('node_id', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['node_id'], ['ref.node.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['app.user_account.id'], ),
        sa.PrimaryKeyConstraint('user_id', 'node_id'),
        schema='app',
    )
    op.create_table(
        'progress',
        sa.Column('user_id', sa.SmallInteger(), nullable=False),
        sa.Column('node_id', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('status_changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('first_done_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_revised_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verify_flag', sa.Boolean(), nullable=False),
        sa.CheckConstraint("status IN ('not_started','in_progress','done')", name='check_progress_status'),
        sa.ForeignKeyConstraint(['node_id'], ['ref.node.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['app.user_account.id'], ),
        sa.PrimaryKeyConstraint('user_id', 'node_id'),
        schema='app',
    )
    op.create_table(
        'progress_event',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.SmallInteger(), nullable=False),
        sa.Column('node_id', sa.Text(), nullable=False),
        sa.Column('from_status', sa.Text(), nullable=True),
        sa.Column('to_status', sa.Text(), nullable=False),
        sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['node_id'], ['ref.node.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='app',
    )
    op.create_index('ix_app_progress_event_user_at', 'progress_event', ['user_id', 'at'], unique=False, schema='app')
    op.create_table(
        'revision_event',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.SmallInteger(), nullable=False),
        sa.Column('node_id', sa.Text(), nullable=False),
        sa.Column('outcome', sa.Text(), nullable=False),
        sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("outcome IN ('ok','shaky')", name='check_revision_outcome'),
        sa.ForeignKeyConstraint(['node_id'], ['ref.node.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='app',
    )
    op.create_table(
        'study_session',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.SmallInteger(), nullable=False),
        sa.Column('node_id', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('minutes', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['node_id'], ['ref.node.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='app',
    )
    op.create_table(
        'appearance_tag',
        sa.Column('appearance_id', sa.BigInteger(), nullable=False),
        sa.Column('node_id', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('share', sa.Float(), nullable=False),
        sa.Column('decision_id', sa.BigInteger(), nullable=False),
        sa.CheckConstraint("role IN ('primary','secondary')", name='check_app_tag_role'),
        sa.CheckConstraint('share > 0 AND share <= 1', name='check_app_tag_share'),
        sa.ForeignKeyConstraint(['appearance_id'], ['core.appearance.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['node_id'], ['ref.node.id'], ),
        sa.PrimaryKeyConstraint('appearance_id', 'node_id'),
        schema='core',
    )
    op.create_index('ix_core_appearance_tag_node', 'appearance_tag', ['node_id'], unique=False, schema='core')
    op.create_table(
        'document',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('blob_path', sa.Text(), nullable=False),
        sa.Column('bytes', sa.BigInteger(), nullable=False),
        sa.Column('origin', sa.Text(), nullable=False),
        sa.Column('scheme_id', sa.Text(), nullable=True),
        sa.Column('attempt_id', sa.Text(), nullable=True),
        sa.Column('paper_id', sa.Text(), nullable=True),
        sa.Column('doc_type_id', sa.Text(), nullable=True),
        sa.Column('series', sa.Text(), nullable=True),
        sa.Column('part', sa.Text(), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('chapter_hint_node_id', sa.Text(), nullable=True),
        sa.Column('catalog_status', sa.Text(), nullable=False),
        sa.Column('extract_status', sa.Text(), nullable=False),
        sa.Column('extract_run_id', sa.BigInteger(), nullable=True),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('has_text_layer', sa.Boolean(), nullable=True),
        sa.Column('ocr_sha256', sa.String(length=64), nullable=True),
        sa.Column('supersedes_document_id', sa.BigInteger(), nullable=True),
        sa.Column('superseded', sa.Boolean(), nullable=False),
        sa.Column('depth_band', sa.Text(), nullable=True),
        sa.Column('created_run_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("catalog_status IN ('inferred','needs_curation','confirmed','rejected')", name='check_document_catalog_status'),
        sa.CheckConstraint("extract_status IN ('pending','running','ok','ok_with_warnings','needs_review','failed','not_applicable')", name='check_document_extract_status'),
        sa.CheckConstraint("origin IN ('http','browser','assisted','manual')", name='check_document_origin'),
        sa.ForeignKeyConstraint(['attempt_id'], ['ref.attempt.id'], ),
        sa.ForeignKeyConstraint(['chapter_hint_node_id'], ['ref.node.id'], ),
        sa.ForeignKeyConstraint(['created_run_id'], ['ops.run.id'], ),
        sa.ForeignKeyConstraint(['doc_type_id'], ['ref.doc_type.id'], ),
        sa.ForeignKeyConstraint(['extract_run_id'], ['ops.run.id'], ),
        sa.ForeignKeyConstraint(['paper_id'], ['ref.paper.id'], ),
        sa.ForeignKeyConstraint(['scheme_id'], ['ref.scheme.id'], ),
        sa.ForeignKeyConstraint(['supersedes_document_id'], ['ingest.document.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sha256'),
        schema='ingest',
    )
    op.create_index('ix_ingest_document_attempt_paper_type', 'document', ['attempt_id', 'paper_id', 'doc_type_id'], unique=False, schema='ingest')
    op.create_index('ix_ingest_document_catalog_extract', 'document', ['catalog_status', 'extract_status'], unique=False, schema='ingest')
    op.create_table(
        'subtopic_score',
        sa.Column('score_run_id', sa.BigInteger(), nullable=False),
        sa.Column('node_id', sa.Text(), nullable=False),
        sa.Column('applicable', sa.Boolean(), nullable=False),
        sa.Column('exam_score', sa.Float(), nullable=False),
        sa.Column('practice_score', sa.Float(), nullable=False),
        sa.Column('weight_prior', sa.Float(), nullable=False),
        sa.Column('importance', sa.Float(), nullable=False),
        sa.Column('freq_hits', sa.Integer(), nullable=False),
        sa.Column('freq_window', sa.Integer(), nullable=False),
        sa.Column('exam_marks_total', sa.Integer(), nullable=False),
        sa.Column('exam_count', sa.Integer(), nullable=False),
        sa.Column('practice_count', sa.Integer(), nullable=False),
        sa.Column('first_exam_attempt', sa.Text(), nullable=True),
        sa.Column('last_exam_attempt', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['node_id'], ['ref.node.id'], ),
        sa.ForeignKeyConstraint(['score_run_id'], ['intel.score_run.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('score_run_id', 'node_id'),
        schema='intel',
    )
    op.create_table(
        'anchor',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('instrument_id', sa.Text(), nullable=False),
        sa.Column('ref_key', sa.Text(), nullable=False),
        sa.Column('node_id', sa.Text(), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['instrument_id'], ['ref.instrument.id'], ),
        sa.ForeignKeyConstraint(['node_id'], ['ref.node.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('instrument_id', 'ref_key', 'node_id', name='uq_anchor_inst_ref_node'),
        schema='ref',
    )
    op.create_index('ix_ref_anchor_lookup', 'anchor', ['instrument_id', 'ref_key'], unique=False, schema='ref')
    op.create_table(
        'applicability_rule',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('attempt_id', sa.Text(), nullable=False),
        sa.Column('node_id', sa.Text(), nullable=False),
        sa.Column('effect', sa.Text(), nullable=False),
        sa.Column('source_note', sa.Text(), nullable=True),
        sa.CheckConstraint("effect IN ('exclude','include')", name='check_applicability_effect'),
        sa.ForeignKeyConstraint(['attempt_id'], ['ref.attempt.id'], ),
        sa.ForeignKeyConstraint(['node_id'], ['ref.node.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='ref',
    )
    op.create_table(
        'descriptor',
        sa.Column('node_id', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('keywords', sa.ARRAY(sa.Text()), nullable=False),
        sa.Column('approved', sa.Boolean(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.CheckConstraint("source IN ('llm_draft','curator')", name='check_descriptor_source'),
        sa.ForeignKeyConstraint(['node_id'], ['ref.node.id'], ),
        sa.PrimaryKeyConstraint('node_id'),
        schema='ref',
    )
    op.create_table(
        'node_version_link',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('old_node_id', sa.Text(), nullable=False),
        sa.Column('new_node_id', sa.Text(), nullable=False),
        sa.Column('relation', sa.Text(), nullable=False),
        sa.Column('taxonomy_version_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("relation IN ('split_into','merged_into','moved')", name='check_version_link_relation'),
        sa.ForeignKeyConstraint(['new_node_id'], ['ref.node.id'], ),
        sa.ForeignKeyConstraint(['old_node_id'], ['ref.node.id'], ),
        sa.ForeignKeyConstraint(['taxonomy_version_id'], ['ref.taxonomy_version.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='ref',
    )
    op.create_table(
        'weightage_member',
        sa.Column('section_id', sa.Text(), nullable=False),
        sa.Column('chapter_id', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['chapter_id'], ['ref.node.id'], ),
        sa.ForeignKeyConstraint(['section_id'], ['ref.weightage_section.id'], ),
        sa.PrimaryKeyConstraint('section_id', 'chapter_id'),
        schema='ref',
    )
    op.create_table(
        'discovered_link',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('source_page_id', sa.BigInteger(), nullable=True),
        sa.Column('anchor_text', sa.Text(), nullable=True),
        sa.Column('breadcrumb', sa.ARRAY(sa.Text()), nullable=True),
        sa.Column('inferred', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('link_status', sa.Text(), nullable=False),
        sa.Column('document_id', sa.BigInteger(), nullable=True),
        sa.Column('tries', sa.Integer(), nullable=False),
        sa.Column('next_try_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("link_status IN ('new','downloaded','failed','manual_required','ignored','not_pdf')", name='check_link_status'),
        sa.ForeignKeyConstraint(['document_id'], ['ingest.document.id'], ),
        sa.ForeignKeyConstraint(['source_page_id'], ['ingest.source_page.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url'),
        schema='ingest',
    )
    op.create_table(
        'unit',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('document_id', sa.BigInteger(), nullable=False),
        sa.Column('extract_run_id', sa.BigInteger(), nullable=False),
        sa.Column('parent_unit_id', sa.BigInteger(), nullable=True),
        sa.Column('label_path', sa.Text(), nullable=False),
        sa.Column('display_label', sa.Text(), nullable=False),
        sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('is_gradable', sa.Boolean(), nullable=False),
        sa.Column('marks', sa.Integer(), nullable=True),
        sa.Column('marks_source', sa.Text(), nullable=True),
        sa.Column('choice_role', sa.Text(), nullable=True),
        sa.Column('or_group', sa.Text(), nullable=True),
        sa.Column('page_start', sa.Integer(), nullable=False),
        sa.Column('page_end', sa.Integer(), nullable=False),
        sa.Column('block_start', sa.Text(), nullable=False),
        sa.Column('block_end', sa.Text(), nullable=False),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('text_origin', sa.Text(), nullable=False),
        sa.Column('fingerprint', sa.String(length=40), nullable=False),
        sa.Column('parse_confidence', sa.Text(), nullable=False),
        sa.Column('validation_flags', sa.ARRAY(sa.Text()), nullable=False),
        sa.Column('classify_status', sa.Text(), nullable=False),
        sa.Column('current', sa.Boolean(), nullable=False),
        sa.CheckConstraint("choice_role IN ('compulsory','optional','unknown')", name='check_unit_choice_role'),
        sa.CheckConstraint("classify_status IN ('pending','running','suggested','failed','skipped','decided','excluded')", name='check_unit_classify_status'),
        sa.CheckConstraint("kind IN ('case_stem','question','part','subpart','mcq')", name='check_unit_kind'),
        sa.CheckConstraint("marks_source IN ('explicit','summed','mcq_default','override','llm_ids')", name='check_unit_marks_source'),
        sa.CheckConstraint("parse_confidence IN ('high','medium','low')", name='check_unit_parse_confidence'),
        sa.CheckConstraint("text_origin IN ('pdf','ocr','llm_transcribed')", name='check_unit_text_origin'),
        sa.CheckConstraint('marks IS NULL OR marks BETWEEN 0 AND 100', name='check_unit_marks'),
        sa.ForeignKeyConstraint(['document_id'], ['ingest.document.id'], ),
        sa.ForeignKeyConstraint(['extract_run_id'], ['ops.run.id'], ),
        sa.ForeignKeyConstraint(['parent_unit_id'], ['ingest.unit.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_id', 'extract_run_id', 'label_path', name='uq_unit_doc_run_label'),
        schema='ingest',
    )
    op.create_index('ix_ingest_unit_fingerprint', 'unit', ['fingerprint'], unique=False, schema='ingest')
    op.create_table(
        'duplicate_link',
        sa.Column('unit_id', sa.BigInteger(), nullable=False),
        sa.Column('other_unit_id', sa.BigInteger(), nullable=False),
        sa.Column('similarity', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['other_unit_id'], ['ingest.unit.id'], ),
        sa.ForeignKeyConstraint(['unit_id'], ['ingest.unit.id'], ),
        sa.PrimaryKeyConstraint('unit_id', 'other_unit_id'),
        schema='ingest',
    )
    op.create_table(
        'tag_suggestion',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('unit_id', sa.BigInteger(), nullable=False),
        sa.Column('run_id', sa.BigInteger(), nullable=False),
        sa.Column('node_id', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('method', sa.Text(), nullable=False),
        sa.Column('bucket', sa.String(length=1), nullable=False),
        sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('model_id', sa.Text(), nullable=True),
        sa.Column('prompt_version', sa.Text(), nullable=True),
        sa.Column('is_shadow', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("bucket IN ('A','B','C','D')", name='check_suggestion_bucket'),
        sa.CheckConstraint("method IN ('structure','anchor','llm','duplicate')", name='check_suggestion_method'),
        sa.CheckConstraint("role IN ('primary','secondary')", name='check_suggestion_role'),
        sa.ForeignKeyConstraint(['node_id'], ['ref.node.id'], ),
        sa.ForeignKeyConstraint(['run_id'], ['ops.run.id'], ),
        sa.ForeignKeyConstraint(['unit_id'], ['ingest.unit.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='ingest',
    )
    op.create_index('ix_ingest_tag_suggestion_unit_shadow', 'tag_suggestion', ['unit_id', 'is_shadow'], unique=False, schema='ingest')
    op.create_table(
        'taxonomy_gap',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('unit_id', sa.BigInteger(), nullable=False),
        sa.Column('run_id', sa.BigInteger(), nullable=True),
        sa.Column('proposed_parent_id', sa.Text(), nullable=True),
        sa.Column('proposed_name', sa.Text(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.CheckConstraint("status IN ('open','resolved_new_node','resolved_existing','ignored')", name='check_gap_status'),
        sa.ForeignKeyConstraint(['proposed_parent_id'], ['ref.node.id'], ),
        sa.ForeignKeyConstraint(['run_id'], ['ops.run.id'], ),
        sa.ForeignKeyConstraint(['unit_id'], ['ingest.unit.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='ingest',
    )
    op.create_table(
        'unit_answer',
        sa.Column('unit_id', sa.BigInteger(), nullable=False),
        sa.Column('answer_document_id', sa.BigInteger(), nullable=False),
        sa.Column('answer_text', sa.Text(), nullable=True),
        sa.Column('page_start', sa.Integer(), nullable=True),
        sa.Column('page_end', sa.Integer(), nullable=True),
        sa.Column('mcq_correct_option', sa.String(length=1), nullable=True),
        sa.Column('pairing_method', sa.Text(), nullable=False),
        sa.CheckConstraint("pairing_method IN ('same_doc','cross_doc','mcq_key','override')", name='check_pairing_method'),
        sa.ForeignKeyConstraint(['answer_document_id'], ['ingest.document.id'], ),
        sa.ForeignKeyConstraint(['unit_id'], ['ingest.unit.id'], ),
        sa.PrimaryKeyConstraint('unit_id'),
        schema='ingest',
    )
    op.create_table(
        'unit_gist',
        sa.Column('unit_id', sa.BigInteger(), nullable=False),
        sa.Column('run_id', sa.BigInteger(), nullable=False),
        sa.Column('gist', sa.Text(), nullable=False),
        sa.Column('model_id', sa.Text(), nullable=True),
        sa.CheckConstraint('char_length(gist) <= 220', name='check_gist_length'),
        sa.ForeignKeyConstraint(['run_id'], ['ops.run.id'], ),
        sa.ForeignKeyConstraint(['unit_id'], ['ingest.unit.id'], ),
        sa.PrimaryKeyConstraint('unit_id', 'run_id'),
        schema='ingest',
    )


def downgrade() -> None:
    op.drop_table('unit_gist', schema='ingest')
    op.drop_table('unit_answer', schema='ingest')
    op.drop_table('taxonomy_gap', schema='ingest')
    op.drop_table('tag_suggestion', schema='ingest')
    op.drop_table('duplicate_link', schema='ingest')
    op.drop_table('unit', schema='ingest')
    op.drop_table('discovered_link', schema='ingest')
    op.drop_table('weightage_member', schema='ref')
    op.drop_table('node_version_link', schema='ref')
    op.drop_table('descriptor', schema='ref')
    op.drop_table('applicability_rule', schema='ref')
    op.drop_table('anchor', schema='ref')
    op.drop_table('subtopic_score', schema='intel')
    op.drop_table('document', schema='ingest')
    op.drop_table('appearance_tag', schema='core')
    op.drop_table('study_session', schema='app')
    op.drop_table('revision_event', schema='app')
    op.drop_table('progress_event', schema='app')
    op.drop_table('progress', schema='app')
    op.drop_table('note', schema='app')
    op.drop_table('weightage_section', schema='ref')
    op.drop_table('node', schema='ref')
    op.drop_table('ingestion_coverage', schema='intel')
    op.drop_table('depth_gate_report', schema='intel')
    op.drop_table('appearance', schema='core')
    op.drop_table('mock_test', schema='app')
    op.drop_table('paper', schema='ref')
    op.drop_table('law_boundary', schema='ref')
    op.drop_table('llm_call', schema='ops')
    op.drop_table('event', schema='ops')
    op.drop_table('score_run', schema='intel')
    op.drop_table('settings', schema='app')
    op.drop_table('taxonomy_version', schema='ref')
    op.drop_table('scheme', schema='ref')
    op.drop_table('instrument', schema='ref')
    op.drop_table('doc_type', schema='ref')
    op.drop_table('attempt', schema='ref')
    op.drop_table('run', schema='ops')
    op.drop_table('source_page', schema='ingest')
    op.drop_table('decision', schema='core')
    op.drop_table('change_log', schema='core')
    op.drop_table('user_account', schema='app')
    for schema in ("app", "intel", "core", "ingest", "ref"):
        op.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
