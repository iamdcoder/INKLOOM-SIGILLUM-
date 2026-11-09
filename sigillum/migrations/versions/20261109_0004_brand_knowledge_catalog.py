"""Move Knowledge Pack catalog, draft state and record decisions into the database.

Revision ID: 20261109_0004
Revises: 20261109_0003
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa

revision = "20261109_0004"
down_revision = "20261109_0003"
branch_labels = None
depends_on = None


def _install_rls() -> None:
    tables = (
        "brand_knowledge_pack_heads",
        "brand_knowledge_pack_versions",
        "brand_knowledge_pack_drafts",
        "brand_knowledge_pack_decisions",
    )
    predicate = (
        "tenant_id = nullif(current_setting('app.tenant_id', true), '') "
        "AND brand_id = nullif(current_setting('app.brand_id', true), '')"
    )
    for table in tables:
        policy = f"sigillum_scope_{table}"
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"')
        op.execute(
            f'CREATE POLICY "{policy}" ON "{table}" '
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )


def upgrade() -> None:
    op.create_table(
        "brand_knowledge_pack_heads",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("brand_id", sa.String(length=100), nullable=False),
        sa.Column("pack_id", sa.String(length=100), nullable=False),
        sa.Column("active_version_id", sa.String(length=40), nullable=False),
        sa.Column("active_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "brand_id", name="uq_brand_knowledge_pack_head_scope"),
    )
    op.create_index("ix_brand_knowledge_pack_heads_tenant_id", "brand_knowledge_pack_heads", ["tenant_id"])
    op.create_index("ix_brand_knowledge_pack_heads_brand_id", "brand_knowledge_pack_heads", ["brand_id"])
    op.create_index("ix_brand_pack_head_scope", "brand_knowledge_pack_heads", ["tenant_id", "brand_id"])

    op.create_table(
        "brand_knowledge_pack_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("brand_id", sa.String(length=100), nullable=False),
        sa.Column("pack_id", sa.String(length=100), nullable=False),
        sa.Column("version_id", sa.String(length=40), nullable=False),
        sa.Column("pack_version", sa.String(length=80), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="PUBLISHED"),
        sa.Column("base_version_id", sa.String(length=40), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "brand_id", "version_id", name="uq_brand_pack_version_scope"),
    )
    op.create_index("ix_brand_knowledge_pack_versions_tenant_id", "brand_knowledge_pack_versions", ["tenant_id"])
    op.create_index("ix_brand_knowledge_pack_versions_brand_id", "brand_knowledge_pack_versions", ["brand_id"])
    op.create_index("ix_brand_pack_version_history", "brand_knowledge_pack_versions", ["tenant_id", "brand_id", "created_at"])

    op.create_table(
        "brand_knowledge_pack_drafts",
        sa.Column("draft_id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("brand_id", sa.String(length=100), nullable=False),
        sa.Column("pack_id", sa.String(length=100), nullable=False),
        sa.Column("base_version_id", sa.String(length=40), nullable=False),
        sa.Column("base_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="DRAFT"),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("validation", sa.JSON(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("published_version_id", sa.String(length=40), nullable=True),
        sa.Column("published_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=120), nullable=False),
    )
    op.create_index("ix_brand_knowledge_pack_drafts_tenant_id", "brand_knowledge_pack_drafts", ["tenant_id"])
    op.create_index("ix_brand_knowledge_pack_drafts_brand_id", "brand_knowledge_pack_drafts", ["brand_id"])
    op.create_index("ix_brand_knowledge_pack_drafts_status", "brand_knowledge_pack_drafts", ["status"])
    op.create_index("ix_brand_pack_draft_scope", "brand_knowledge_pack_drafts", ["tenant_id", "brand_id", "status"])
    op.create_index("ix_brand_pack_draft_updated", "brand_knowledge_pack_drafts", ["tenant_id", "brand_id", "updated_at"])

    op.create_table(
        "brand_knowledge_pack_decisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("brand_id", sa.String(length=100), nullable=False),
        sa.Column("draft_id", sa.String(length=36), nullable=False),
        sa.Column("record_type", sa.String(length=40), nullable=False),
        sa.Column("record_id", sa.String(length=120), nullable=False),
        sa.Column("decision_status", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_brand_knowledge_pack_decisions_tenant_id", "brand_knowledge_pack_decisions", ["tenant_id"])
    op.create_index("ix_brand_knowledge_pack_decisions_brand_id", "brand_knowledge_pack_decisions", ["brand_id"])
    op.create_index("ix_brand_knowledge_pack_decisions_draft_id", "brand_knowledge_pack_decisions", ["draft_id"])
    op.create_index("ix_brand_pack_decision_record", "brand_knowledge_pack_decisions", ["tenant_id", "brand_id", "record_type", "record_id"])
    op.create_index("ix_brand_pack_decision_draft", "brand_knowledge_pack_decisions", ["draft_id", "created_at"])

    if op.get_bind().dialect.name == "postgresql":
        _install_rls()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "brand_knowledge_pack_decisions",
            "brand_knowledge_pack_drafts",
            "brand_knowledge_pack_versions",
            "brand_knowledge_pack_heads",
        ):
            op.execute(f'DROP POLICY IF EXISTS "sigillum_scope_{table}" ON "{table}"')
            op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
    op.drop_table("brand_knowledge_pack_decisions")
    op.drop_table("brand_knowledge_pack_drafts")
    op.drop_table("brand_knowledge_pack_versions")
    op.drop_table("brand_knowledge_pack_heads")
