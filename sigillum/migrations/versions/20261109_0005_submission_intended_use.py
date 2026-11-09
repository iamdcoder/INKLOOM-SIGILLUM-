"""Add explicit intended-use context for deterministic brand-asset policy checks.

Revision ID: 20261109_0005
Revises: 20261109_0004
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa

revision = "20261109_0005"
down_revision = "20261109_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("submissions")}
    # Fresh installs may already have the column because the initial bootstrap
    # creates current ORM metadata before walking the historical revisions.
    if "intended_use" not in columns:
        op.add_column(
            "submissions",
            sa.Column("intended_use", sa.String(length=40), nullable=False, server_default="general"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("submissions")}
    if "intended_use" in columns:
        op.drop_column("submissions", "intended_use")
