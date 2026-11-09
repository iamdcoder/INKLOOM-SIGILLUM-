"""Initial Sigillum schema.

Revision ID: 20261108_0001
Revises:
Create Date: 2026-11-08
"""
from alembic import op
from sigillum.infrastructure.database.session import Base
from sigillum.infrastructure.database import models  # noqa: F401

revision = "20261108_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Freeze the original schema boundary. Later model additions must arrive
    # through their own Alembic revisions rather than silently appearing in
    # a fresh-install replay of this historical migration.
    later_tables = {
        "brand_knowledge_pack_heads",
        "brand_knowledge_pack_versions",
        "brand_knowledge_pack_drafts",
        "brand_knowledge_pack_decisions",
    }
    initial_tables = [table for table in Base.metadata.sorted_tables if table.name not in later_tables]
    Base.metadata.create_all(bind=op.get_bind(), tables=initial_tables)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
