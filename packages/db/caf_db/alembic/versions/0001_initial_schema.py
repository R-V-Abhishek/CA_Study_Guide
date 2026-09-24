"""Initial schema migration for CAF.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-24 20:52:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from caf_db.models.base import Base
import caf_db.models

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    schemas = ["ops", "ref", "ingest", "core", "intel", "app"]
    for s in schemas:
        conn.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {s};"))

    Base.metadata.create_all(bind=conn)


def downgrade() -> None:
    conn = op.get_bind()
    Base.metadata.drop_all(bind=conn)
    schemas = ["app", "intel", "core", "ingest", "ref"]
    for s in schemas:
        conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {s} CASCADE;"))
