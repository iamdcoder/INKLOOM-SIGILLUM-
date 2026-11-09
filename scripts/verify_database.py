"""Verify a migrated database before starting the API or deploying."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import inspect, text

from sigillum.config import get_settings
from sigillum.infrastructure.database.migrations import get_migration_status
from sigillum.infrastructure.database.session import Base, create_database_engine
from sigillum.infrastructure.database import models  # noqa: F401


RLS_TABLES = (
    "tenants",
    "brands",
    "memberships",
    "user_sessions",
    "submissions",
    "content_versions",
    "review_runs",
    "findings",
    "patches",
    "decisions",
    "audit_events",
    "brand_knowledge_pack_heads",
    "brand_knowledge_pack_versions",
    "brand_knowledge_pack_drafts",
    "brand_knowledge_pack_decisions",
)
RLS_REQUIRED_POLICY_COUNTS = {"memberships": 3}


def _verify_postgresql_rls(connection) -> dict:
    placeholders = ", ".join(f":table_{index}" for index in range(len(RLS_TABLES)))
    params = {f"table_{index}": table for index, table in enumerate(RLS_TABLES)}
    rows = connection.execute(
        text(
            "SELECT relname, relrowsecurity, relforcerowsecurity "
            "FROM pg_class "
            "WHERE relnamespace = current_schema()::regnamespace "
            f"AND relname IN ({placeholders})"
        ),
        params,
    ).mappings().all()
    by_name = {row["relname"]: row for row in rows}
    table_report = []
    for table in RLS_TABLES:
        row = by_name.get(table)
        policy_count = connection.execute(
            text(
                "SELECT count(*) FROM pg_policies "
                "WHERE schemaname = current_schema() AND tablename = :table"
            ),
            {"table": table},
        ).scalar_one()
        table_report.append(
            {
                "table": table,
                "exists": row is not None,
                "enabled": bool(row["relrowsecurity"]) if row else False,
                "forced": bool(row["relforcerowsecurity"]) if row else False,
                "policy_count": int(policy_count),
                "required_policy_count": RLS_REQUIRED_POLICY_COUNTS.get(table, 1),
            }
        )
    complete = all(
        item["exists"]
        and item["enabled"]
        and item["forced"]
        and item["policy_count"] >= item["required_policy_count"]
        for item in table_report
    )
    return {"status": "enforced" if complete else "incomplete", "tables": table_report}


def main() -> int:
    settings = get_settings()
    engine = create_database_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout_seconds=settings.database_pool_timeout_seconds,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            migration = get_migration_status(connection, settings)
            inspector = inspect(connection)
            actual_tables = set(inspector.get_table_names())
            required_tables = set(Base.metadata.tables)
            missing_tables = sorted(required_tables - actual_tables)
            vector_extension = None
            if engine.dialect.name == "postgresql":
                vector_extension = connection.execute(
                    text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
                ).scalar_one()
                row_level_security = _verify_postgresql_rls(connection)
            else:
                row_level_security = {"status": "not_applicable", "tables": []}

            report = {
                "database_dialect": engine.dialect.name,
                "migration": migration,
                "required_tables": sorted(required_tables),
                "missing_tables": missing_tables,
                "pgvector_extension": vector_extension,
                "row_level_security": row_level_security,
            }
            print(json.dumps(report, indent=2, default=str))

            valid = (
                migration["status"] == "current"
                and not missing_tables
                and (engine.dialect.name != "postgresql" or vector_extension is True)
                and (engine.dialect.name != "postgresql" or row_level_security["status"] == "enforced")
            )
            return 0 if valid else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
