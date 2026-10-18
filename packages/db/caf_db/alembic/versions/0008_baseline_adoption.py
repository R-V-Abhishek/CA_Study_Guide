"""Shared catalogs and explicit frozen-corpus adoption, without verification claims."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0008_baseline_adoption'
down_revision = '0007_question_reader'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('candidate_catalog',
        sa.Column('content_hash', sa.Text(), primary_key=True),
        sa.Column('candidates', JSONB(), nullable=False), schema='ref')
    op.add_column('suggestion_revision', sa.Column('candidate_catalog_hash', sa.Text(),
        sa.ForeignKey('ref.candidate_catalog.content_hash')), schema='ingest')
    op.create_table('baseline_adoption',
        sa.Column('release_id', sa.Text(), sa.ForeignKey('ref.taxonomy_release.version_id'), primary_key=True),
        sa.Column('manifest_hash', sa.Text(), nullable=False),
        sa.Column('manifest', JSONB(), nullable=False),
        sa.Column('pins', JSONB(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('app.user_account.id'), nullable=False),
        sa.Column('previous_state', JSONB(), nullable=False),
        sa.Column('activated_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('prepared','active','inactive')"), schema='core')


def downgrade():
    op.drop_table('baseline_adoption', schema='core')
    op.drop_column('suggestion_revision', 'candidate_catalog_hash', schema='ingest')
    op.drop_table('candidate_catalog', schema='ref')
