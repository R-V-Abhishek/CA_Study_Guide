"""Store effective scoring configuration for future score explanations.

Legacy rows deliberately remain NULL. No historical configuration is inferred.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002_score_config_snapshot'
down_revision = '0001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('score_run', sa.Column('config_snapshot', postgresql.JSONB(), nullable=True), schema='intel')


def downgrade() -> None:
    op.drop_column('score_run', 'config_snapshot', schema='intel')
