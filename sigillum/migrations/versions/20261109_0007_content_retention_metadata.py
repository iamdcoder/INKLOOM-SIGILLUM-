"""Add explicit retention metadata to immutable submission versions.

Revision ID: 20261109_0007
Revises: 20261109_0006
Create Date: 2026-11-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261109_0007"
down_revision = "20261109_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {item["name"] for item in sa.inspect(connection).get_columns("content_versions")}
    if "retention_policy" not in columns:
        op.add_column(
            "content_versions",
            sa.Column("retention_policy", sa.String(length=80), nullable=False, server_default="MANUAL"),
        )
    if "retention_until" not in columns:
        op.add_column(
            "content_versions",
            sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("content_versions")}
    if "retention_until" in columns:
        op.drop_column("content_versions", "retention_until")
    if "retention_policy" in columns:
        op.drop_column("content_versions", "retention_policy")
