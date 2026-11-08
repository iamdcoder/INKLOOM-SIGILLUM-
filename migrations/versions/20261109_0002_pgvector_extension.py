"""Install pgvector on PostgreSQL installations.

Revision ID: 20261109_0002
Revises: 20261108_0001
Create Date: 2026-11-09
"""
from alembic import op

revision = "20261109_0002"
down_revision = "20261108_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # The extension is deliberately retained on downgrade because it may be
        # shared by other application schemas in the same PostgreSQL cluster.
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Do not drop a cluster-level extension that may be used by other databases.
    pass
