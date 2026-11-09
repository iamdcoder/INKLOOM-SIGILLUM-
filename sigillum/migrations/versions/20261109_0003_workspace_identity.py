"""Workspace identity, brand memberships, revocable sessions and RLS.

Revision ID: 20261109_0003
Revises: 20261109_0002
Create Date: 2026-11-09
"""
from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "20261109_0003"
down_revision = "20261109_0002"
branch_labels = None
depends_on = None


def _table_exists(connection, name: str) -> bool:
    return sa.inspect(connection).has_table(name)


def _brand_for_entity(connection, entity_type: str, entity_id: str):
    lookups = {
        "submission": "SELECT brand_id FROM submissions WHERE id=:entity_id",
        "content_version": (
            "SELECT s.brand_id FROM content_versions v "
            "JOIN submissions s ON s.id=v.submission_id WHERE v.id=:entity_id"
        ),
        "review": (
            "SELECT s.brand_id FROM review_runs r "
            "JOIN submissions s ON s.id=r.submission_id WHERE r.id=:entity_id"
        ),
        "finding": (
            "SELECT s.brand_id FROM findings f JOIN review_runs r ON r.id=f.review_id "
            "JOIN submissions s ON s.id=r.submission_id WHERE f.id=:entity_id"
        ),
        "patch": (
            "SELECT s.brand_id FROM patches p JOIN review_runs r ON r.id=p.review_id "
            "JOIN submissions s ON s.id=r.submission_id WHERE p.id=:entity_id"
        ),
    }
    query = lookups.get(entity_type)
    if not query:
        return None
    return connection.execute(text(query), {"entity_id": entity_id}).scalar_one_or_none()


def _backfill_workspace_records(connection) -> None:
    tenant_ids: set[str] = set()
    for table in ("users", "submissions", "audit_events"):
        if _table_exists(connection, table):
            tenant_ids.update(
                value
                for value in connection.execute(text(f"SELECT DISTINCT tenant_id FROM {table}")).scalars()
                if value
            )

    for tenant_id in sorted(tenant_ids):
        connection.execute(
            text(
                "INSERT INTO tenants (id, name, is_active, created_at) "
                "VALUES (:id, :name, true, CURRENT_TIMESTAMP) ON CONFLICT (id) DO NOTHING"
            ),
            {"id": tenant_id, "name": "ORBITA Demo Workspace" if tenant_id == "tenant_demo" else tenant_id},
        )

    brand_rows: list[tuple[str, str]] = []
    if _table_exists(connection, "submissions"):
        brand_rows = [
            (tenant_id, brand_id)
            for tenant_id, brand_id in connection.execute(
                text(
                    "SELECT DISTINCT tenant_id, brand_id FROM submissions "
                    "WHERE tenant_id IS NOT NULL AND brand_id IS NOT NULL"
                )
            )
        ]

    brands_by_tenant: dict[str, list[tuple[str, str]]] = {tenant_id: [] for tenant_id in tenant_ids}
    for tenant_id, external_id in brand_rows:
        brands_by_tenant.setdefault(tenant_id, []).append(
            (external_id, "ORBITA" if external_id == "brand_orbita_demo" else external_id)
        )

    for tenant_id in sorted(tenant_ids):
        if not brands_by_tenant.get(tenant_id):
            brands_by_tenant[tenant_id] = [("brand_orbita_demo", "ORBITA")]
        for external_id, name in brands_by_tenant[tenant_id]:
            found = connection.execute(
                text("SELECT id FROM brands WHERE tenant_id=:tenant_id AND external_id=:external_id"),
                {"tenant_id": tenant_id, "external_id": external_id},
            ).scalar_one_or_none()
            if found:
                continue
            connection.execute(
                text(
                    "INSERT INTO brands (id, tenant_id, external_id, name, is_active, created_at) "
                    "VALUES (:id, :tenant_id, :external_id, :name, true, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": str(uuid4()),
                    "tenant_id": tenant_id,
                    "external_id": external_id,
                    "name": name,
                },
            )

    # A legacy single-brand tenant has an unambiguous workspace scope, so all
    # of its existing users retain access to that one brand. For a tenant that
    # already contains multiple brands, infer only the specific brands evidenced
    # by a user's own submissions or attributed audit events. Never grant every
    # legacy user access to every brand merely because they share a tenant.
    if _table_exists(connection, "users"):
        users = connection.execute(text("SELECT id, tenant_id, role FROM users")).all()
        for user_id, tenant_id, role in users:
            brands = connection.execute(
                text("SELECT id, external_id FROM brands WHERE tenant_id=:tenant_id"),
                {"tenant_id": tenant_id},
            ).all()
            if len(brands) == 1:
                target_brand_ids = [brands[0][0]]
            else:
                associated_external_ids = set(
                    connection.execute(
                        text(
                            "SELECT DISTINCT brand_id FROM submissions "
                            "WHERE tenant_id=:tenant_id AND created_by=:user_id AND brand_id IS NOT NULL"
                        ),
                        {"tenant_id": tenant_id, "user_id": user_id},
                    ).scalars()
                )
                if _table_exists(connection, "audit_events"):
                    actor_events = connection.execute(
                        text(
                            "SELECT entity_type, entity_id FROM audit_events "
                            "WHERE tenant_id=:tenant_id AND actor_id=:user_id"
                        ),
                        {"tenant_id": tenant_id, "user_id": user_id},
                    ).all()
                    for entity_type, entity_id in actor_events:
                        external_id = _brand_for_entity(connection, entity_type, entity_id)
                        if external_id:
                            associated_external_ids.add(external_id)
                target_brand_ids = [
                    brand_record_id
                    for brand_record_id, external_id in brands
                    if external_id in associated_external_ids
                ]

            for brand_record_id in target_brand_ids:
                exists = connection.execute(
                    text("SELECT 1 FROM memberships WHERE user_id=:user_id AND brand_id=:brand_id"),
                    {"user_id": user_id, "brand_id": brand_record_id},
                ).first()
                if not exists:
                    connection.execute(
                        text(
                            "INSERT INTO memberships "
                            "(id, user_id, tenant_id, brand_id, role, is_active, created_at) "
                            "VALUES (:id, :user_id, :tenant_id, :brand_id, :role, true, CURRENT_TIMESTAMP)"
                        ),
                        {
                            "id": str(uuid4()),
                            "user_id": user_id,
                            "tenant_id": tenant_id,
                            "brand_id": brand_record_id,
                            "role": role if role in {"creator", "agency", "reviewer", "brand_owner", "administrator"} else "creator",
                        },
                    )

    if _table_exists(connection, "audit_events"):
        events = connection.execute(
            text("SELECT id, tenant_id, entity_type, entity_id FROM audit_events WHERE brand_id IS NULL")
        ).all()
        for event_id, tenant_id, entity_type, entity_id in events:
            brand_external_id = _brand_for_entity(connection, entity_type, entity_id)
            if not brand_external_id:
                possible = connection.execute(
                    text("SELECT external_id FROM brands WHERE tenant_id=:tenant_id"),
                    {"tenant_id": tenant_id},
                ).scalars().all()
                if len(possible) == 1:
                    brand_external_id = possible[0]
            if brand_external_id:
                connection.execute(
                    text("UPDATE audit_events SET brand_id=:brand_id WHERE id=:event_id"),
                    {"brand_id": brand_external_id, "event_id": event_id},
                )


def _install_postgresql_rls() -> None:
    policies = {
        "tenants": "id = nullif(current_setting('app.tenant_id', true), '') "
                   "OR id IN (SELECT tenant_id FROM memberships WHERE user_id = nullif(current_setting('app.user_id', true), ''))",
        "brands": "id IN (SELECT brand_id FROM memberships WHERE user_id = nullif(current_setting('app.user_id', true), '')) "
                  "OR (tenant_id = nullif(current_setting('app.tenant_id', true), '') "
                  "AND external_id = nullif(current_setting('app.brand_id', true), ''))",
        "user_sessions": "user_id = nullif(current_setting('app.user_id', true), '')",
        "submissions": "tenant_id = nullif(current_setting('app.tenant_id', true), '') "
                       "AND brand_id = nullif(current_setting('app.brand_id', true), '')",
        "content_versions": "EXISTS (SELECT 1 FROM submissions s WHERE s.id = content_versions.submission_id "
                            "AND s.tenant_id = nullif(current_setting('app.tenant_id', true), '') "
                            "AND s.brand_id = nullif(current_setting('app.brand_id', true), ''))",
        "review_runs": "EXISTS (SELECT 1 FROM submissions s WHERE s.id = review_runs.submission_id "
                       "AND s.tenant_id = nullif(current_setting('app.tenant_id', true), '') "
                       "AND s.brand_id = nullif(current_setting('app.brand_id', true), ''))",
        "findings": "EXISTS (SELECT 1 FROM review_runs r JOIN submissions s ON s.id = r.submission_id "
                    "WHERE r.id = findings.review_id AND s.tenant_id = nullif(current_setting('app.tenant_id', true), '') "
                    "AND s.brand_id = nullif(current_setting('app.brand_id', true), ''))",
        "patches": "EXISTS (SELECT 1 FROM review_runs r JOIN submissions s ON s.id = r.submission_id "
                   "WHERE r.id = patches.review_id AND s.tenant_id = nullif(current_setting('app.tenant_id', true), '') "
                   "AND s.brand_id = nullif(current_setting('app.brand_id', true), ''))",
        "decisions": "EXISTS (SELECT 1 FROM submissions s WHERE s.id = decisions.submission_id "
                     "AND s.tenant_id = nullif(current_setting('app.tenant_id', true), '') "
                     "AND s.brand_id = nullif(current_setting('app.brand_id', true), ''))",
        "audit_events": "tenant_id = nullif(current_setting('app.tenant_id', true), '') "
                        "AND brand_id = nullif(current_setting('app.brand_id', true), '')",
    }
    for table, predicate in policies.items():
        policy_name = f"sigillum_scope_{table}"
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS "{policy_name}" ON "{table}"')
        if table == "tenants":
            check = "id = nullif(current_setting('app.tenant_id', true), '')"
        elif table == "brands":
            check = (
                "tenant_id = nullif(current_setting('app.tenant_id', true), '') "
                "AND external_id = nullif(current_setting('app.brand_id', true), '')"
            )
        elif table == "audit_events":
            check = (
                "tenant_id = nullif(current_setting('app.tenant_id', true), '') "
                "AND brand_id = nullif(current_setting('app.brand_id', true), '')"
            )
        else:
            check = predicate
        op.execute(
            f'CREATE POLICY "{policy_name}" ON "{table}" '
            f"USING ({predicate}) WITH CHECK ({check})"
        )

    # Membership data needs command-specific policies. A user's own membership
    # is readable, but that must never imply permission to modify their own role.
    # Administrators can manage membership rows in the selected brand. Brand
    # Owners can add only contributor-level roles and cannot update/delete rows.
    op.execute('ALTER TABLE "memberships" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "memberships" FORCE ROW LEVEL SECURITY')
    for policy_name in (
        "sigillum_scope_memberships",
        "sigillum_memberships_select",
        "sigillum_memberships_insert",
        "sigillum_memberships_update",
    ):
        op.execute(f'DROP POLICY IF EXISTS "{policy_name}" ON "memberships"')
    selected_brand = (
        "tenant_id = nullif(current_setting('app.tenant_id', true), '') "
        "AND brand_id = nullif(current_setting('app.brand_record_id', true), '')"
    )
    owner_or_admin = selected_brand + " AND nullif(current_setting('app.membership_role', true), '') IN ('administrator', 'brand_owner')"
    admin_only = selected_brand + " AND nullif(current_setting('app.membership_role', true), '') = 'administrator'"
    owner_insert = (
        selected_brand
        + " AND nullif(current_setting('app.membership_role', true), '') = 'brand_owner' "
        + "AND role IN ('creator', 'agency', 'reviewer')"
    )
    op.execute(
        'CREATE POLICY "sigillum_memberships_select" ON "memberships" '
        "FOR SELECT USING (user_id = nullif(current_setting('app.user_id', true), '') OR (" + owner_or_admin + "))"
    )
    op.execute(
        'CREATE POLICY "sigillum_memberships_insert" ON "memberships" '
        "FOR INSERT WITH CHECK ((" + admin_only + ") OR (" + owner_insert + "))"
    )
    op.execute(
        'CREATE POLICY "sigillum_memberships_update" ON "memberships" '
        "FOR UPDATE USING (" + admin_only + ") WITH CHECK (" + admin_only + ")"
    )



def _create_index_if_missing(connection, name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    existing = {item["name"] for item in sa.inspect(connection).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # The original 0001 migration creates tables from the live ORM metadata.
    # On a fresh install this may already include these newly-added models.
    # Existing Build 010 databases do not, so create each object conditionally.
    if not inspector.has_table("tenants"):
        op.create_table(
            "tenants",
            sa.Column("id", sa.String(length=80), primary_key=True),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    _create_index_if_missing(connection, "ix_tenants_is_active", "tenants", ["is_active"])

    if not inspector.has_table("brands"):
        op.create_table(
            "brands",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=80), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("external_id", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "external_id", name="uq_brand_tenant_external_id"),
        )
    _create_index_if_missing(connection, "ix_brands_tenant_id", "brands", ["tenant_id"])
    _create_index_if_missing(connection, "ix_brands_external_id", "brands", ["external_id"])
    _create_index_if_missing(connection, "ix_brands_is_active", "brands", ["is_active"])

    if not inspector.has_table("memberships"):
        op.create_table(
            "memberships",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("tenant_id", sa.String(length=80), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("brand_id", sa.String(length=36), sa.ForeignKey("brands.id"), nullable=False),
            sa.Column("role", sa.String(length=40), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "brand_id", name="uq_membership_user_brand"),
        )
    _create_index_if_missing(connection, "ix_memberships_user_id", "memberships", ["user_id"])
    _create_index_if_missing(connection, "ix_memberships_tenant_id", "memberships", ["tenant_id"])
    _create_index_if_missing(connection, "ix_memberships_brand_id", "memberships", ["brand_id"])
    _create_index_if_missing(connection, "ix_memberships_role", "memberships", ["role"])
    _create_index_if_missing(connection, "ix_memberships_is_active", "memberships", ["is_active"])
    _create_index_if_missing(connection, "ix_memberships_user_active", "memberships", ["user_id", "is_active"])
    _create_index_if_missing(connection, "ix_memberships_tenant_brand", "memberships", ["tenant_id", "brand_id"])

    if not inspector.has_table("user_sessions"):
        op.create_table(
            "user_sessions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("membership_id", sa.String(length=36), sa.ForeignKey("memberships.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )
    _create_index_if_missing(connection, "ix_user_sessions_user_id", "user_sessions", ["user_id"])
    _create_index_if_missing(connection, "ix_user_sessions_membership_id", "user_sessions", ["membership_id"])
    _create_index_if_missing(connection, "ix_user_sessions_expires_at", "user_sessions", ["expires_at"])

    columns = {item["name"] for item in sa.inspect(connection).get_columns("audit_events")}
    if "brand_id" not in columns:
        op.add_column("audit_events", sa.Column("brand_id", sa.String(length=80), nullable=True))
    _create_index_if_missing(connection, "ix_audit_events_brand_id", "audit_events", ["brand_id"])

    _backfill_workspace_records(connection)
    if connection.dialect.name == "postgresql":
        _install_postgresql_rls()


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        for table in (
            "tenants", "brands", "memberships", "user_sessions", "submissions", "content_versions",
            "review_runs", "findings", "patches", "decisions", "audit_events",
        ):
            policy_name = f"sigillum_scope_{table}"
            op.execute(f'DROP POLICY IF EXISTS "{policy_name}" ON "{table}"')
            if table == "memberships":
                for membership_policy in ("sigillum_memberships_select", "sigillum_memberships_insert", "sigillum_memberships_update"):
                    op.execute(f'DROP POLICY IF EXISTS "{membership_policy}" ON "{table}"')
            op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
    op.drop_index("ix_audit_events_brand_id", table_name="audit_events")
    op.drop_column("audit_events", "brand_id")
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_membership_id", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_memberships_tenant_brand", table_name="memberships")
    op.drop_index("ix_memberships_user_active", table_name="memberships")
    for index in ("ix_memberships_is_active", "ix_memberships_role", "ix_memberships_brand_id", "ix_memberships_tenant_id", "ix_memberships_user_id"):
        op.drop_index(index, table_name="memberships")
    op.drop_table("memberships")
    for index in ("ix_brands_is_active", "ix_brands_external_id", "ix_brands_tenant_id"):
        op.drop_index(index, table_name="brands")
    op.drop_table("brands")
    op.drop_index("ix_tenants_is_active", table_name="tenants")
    op.drop_table("tenants")
