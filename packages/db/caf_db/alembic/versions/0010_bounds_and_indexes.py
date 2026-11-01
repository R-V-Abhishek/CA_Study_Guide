"""Bound free-text lengths and index per-student lookups; no existing row is changed."""
from alembic import op
import sqlalchemy as sa

revision = '0010_bounds_and_indexes'
down_revision = '0009_question_language'
branch_labels = None
depends_on = None

BOUNDS = [
    ('app', 'note', 'body', 100_000, 'check_note_body_length'),
    ('app', 'mock_test', 'label', 200, 'check_mock_test_label_length'),
    ('app', 'mock_test', 'notes', 10_000, 'check_mock_test_notes_length'),
]
INDEXES = [
    ('ix_revision_event_user_node_at', 'revision_event', ['user_id', 'node_id', 'at']),
    ('ix_mock_test_user_taken_on', 'mock_test', ['user_id', 'taken_on']),
    ('ix_study_session_user_id', 'study_session', ['user_id']),
]


def upgrade():
    connection = op.get_bind()
    for schema, table, column, limit, name in BOUNDS:
        op.execute(f'ALTER TABLE {schema}.{table} ADD CONSTRAINT {name} '
                   f'CHECK ({column} IS NULL OR char_length({column}) <= {limit}) NOT VALID')
        oversized = connection.execute(sa.text(
            f'SELECT count(*) FROM {schema}.{table} WHERE char_length({column}) > {limit}')).scalar_one()
        if oversized == 0:
            op.execute(f'ALTER TABLE {schema}.{table} VALIDATE CONSTRAINT {name}')
        # Otherwise the constraint stays NOT VALID: it still rejects new oversized
        # values, and personal text already stored is never truncated.
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns, schema='app')


def downgrade():
    raise RuntimeError('Forward-only migration: restore a verified recovery snapshot instead')
