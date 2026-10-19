"""Persist each student's opt-in to Hindi question content."""
from alembic import op
import sqlalchemy as sa

revision = '0009_question_language'
down_revision = '0008_baseline_adoption'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('settings', sa.Column('include_hindi', sa.Boolean(), nullable=False,
                                      server_default=sa.false()), schema='app')


def downgrade():
    op.drop_column('settings', 'include_hindi', schema='app')
