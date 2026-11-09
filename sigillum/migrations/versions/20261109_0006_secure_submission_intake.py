"""Add secure-upload provenance, idempotency reservations and review outbox rows.

Revision ID: 20261109_0006
Revises: 20261109_0005
Create Date: 2026-11-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261109_0006"
down_revision = "20261109_0005"
branch_labels = None
depends_on = None


def _create_index_if_missing(connection, name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    existing = {item["name"] for item in sa.inspect(connection).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    submission_columns = {item["name"] for item in inspector.get_columns("submissions")}
    for name, column in (
        ("product_scope", sa.Column("product_scope", sa.String(length=160), nullable=True)),
        ("campaign_scope", sa.Column("campaign_scope", sa.String(length=160), nullable=True)),
        ("context_note", sa.Column("context_note", sa.Text(), nullable=True)),
    ):
        if name not in submission_columns:
            op.add_column("submissions", column)

    version_columns = {item["name"] for item in sa.inspect(connection).get_columns("content_versions")}
    version_additions = (
        ("parent_version_id", sa.Column("parent_version_id", sa.String(length=36), nullable=True)),
        ("scan_status", sa.Column("scan_status", sa.String(length=24), nullable=False, server_default="CLEAN")),
        ("scan_engine", sa.Column("scan_engine", sa.String(length=80), nullable=True)),
        ("scan_scanned_at", sa.Column("scan_scanned_at", sa.String(length=40), nullable=True)),
        ("scan_signature", sa.Column("scan_signature", sa.String(length=255), nullable=True)),
    )
    for name, column in version_additions:
        if name not in version_columns:
            op.add_column("content_versions", column)
    _create_index_if_missing(connection, "ix_content_versions_parent_version_id", "content_versions", ["parent_version_id"])

    if not inspector.has_table("submission_upload_requests"):
        op.create_table(
            "submission_upload_requests",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("brand_id", sa.String(length=80), nullable=False),
            sa.Column("actor_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("idempotency_key", sa.String(length=100), nullable=False),
            sa.Column("payload_sha256", sa.String(length=64), nullable=False),
            sa.Column("submission_id", sa.String(length=36), sa.ForeignKey("submissions.id"), nullable=False),
            sa.Column("content_version_id", sa.String(length=36), nullable=True),
            sa.Column("review_id", sa.String(length=36), nullable=True),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="PROCESSING"),
            sa.Column("error_code", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint(
                "tenant_id", "brand_id", "actor_id", "idempotency_key",
                name="uq_submission_upload_idempotency",
            ),
        )
    _create_index_if_missing(connection, "ix_submission_upload_requests_tenant_id", "submission_upload_requests", ["tenant_id"])
    _create_index_if_missing(connection, "ix_submission_upload_requests_brand_id", "submission_upload_requests", ["brand_id"])
    _create_index_if_missing(connection, "ix_submission_upload_requests_actor_id", "submission_upload_requests", ["actor_id"])
    _create_index_if_missing(connection, "ix_submission_upload_requests_submission_id", "submission_upload_requests", ["submission_id"])
    _create_index_if_missing(connection, "ix_submission_upload_requests_status", "submission_upload_requests", ["status"])
    _create_index_if_missing(connection, "ix_submission_upload_scope_status", "submission_upload_requests", ["tenant_id", "brand_id", "status"])

    if not inspector.has_table("review_jobs"):
        op.create_table(
            "review_jobs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), nullable=False),
            sa.Column("brand_id", sa.String(length=80), nullable=False),
            sa.Column("submission_id", sa.String(length=36), sa.ForeignKey("submissions.id"), nullable=False),
            sa.Column("content_version_id", sa.String(length=36), sa.ForeignKey("content_versions.id"), nullable=False),
            sa.Column("job_type", sa.String(length=40), nullable=False, server_default="BRAND_ASSURANCE_REVIEW"),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="QUEUED"),
            sa.Column("context_snapshot", sa.JSON(), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_code", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("content_version_id", "job_type", name="uq_review_job_version_type"),
        )
    _create_index_if_missing(connection, "ix_review_jobs_tenant_id", "review_jobs", ["tenant_id"])
    _create_index_if_missing(connection, "ix_review_jobs_brand_id", "review_jobs", ["brand_id"])
    _create_index_if_missing(connection, "ix_review_jobs_submission_id", "review_jobs", ["submission_id"])
    _create_index_if_missing(connection, "ix_review_jobs_content_version_id", "review_jobs", ["content_version_id"])
    _create_index_if_missing(connection, "ix_review_jobs_status", "review_jobs", ["status"])
    _create_index_if_missing(connection, "ix_review_jobs_scope_status", "review_jobs", ["tenant_id", "brand_id", "status"])

    if connection.dialect.name == "postgresql":
        workspace_scope = (
            "tenant_id = nullif(current_setting('app.tenant_id', true), '') "
            "AND brand_id = nullif(current_setting('app.brand_id', true), '')"
        )
        upload_scope = workspace_scope + " AND actor_id = nullif(current_setting('app.user_id', true), '')"
        for table, predicate in (
            ("submission_upload_requests", upload_scope),
            ("review_jobs", workspace_scope),
        ):
            policy_name = f"sigillum_scope_{table}"
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(f'DROP POLICY IF EXISTS "{policy_name}" ON "{table}"')
            op.execute(
                f'CREATE POLICY "{policy_name}" ON "{table}" '
                f"USING ({predicate}) WITH CHECK ({predicate})"
            )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        for table in ("submission_upload_requests", "review_jobs"):
            op.execute(f'DROP POLICY IF EXISTS "sigillum_scope_{table}" ON "{table}"')
            op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')

    inspector = sa.inspect(connection)
    if inspector.has_table("review_jobs"):
        op.drop_table("review_jobs")
    if inspector.has_table("submission_upload_requests"):
        op.drop_table("submission_upload_requests")
    version_columns = {item["name"] for item in sa.inspect(connection).get_columns("content_versions")}
    if "parent_version_id" in version_columns:
        op.drop_index("ix_content_versions_parent_version_id", table_name="content_versions")
    for name in ("scan_signature", "scan_scanned_at", "scan_engine", "scan_status", "parent_version_id"):
        if name in version_columns:
            op.drop_column("content_versions", name)
    submission_columns = {item["name"] for item in sa.inspect(connection).get_columns("submissions")}
    for name in ("context_note", "campaign_scope", "product_scope"):
        if name in submission_columns:
            op.drop_column("submissions", name)
