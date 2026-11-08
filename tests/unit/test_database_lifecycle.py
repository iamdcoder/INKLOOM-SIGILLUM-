from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from pydantic import ValidationError

from sigillum.config import Settings
from sigillum.infrastructure.database.migrations import (
    get_migration_status,
    upgrade_database,
)
from sigillum.infrastructure.database.session import create_database_engine, normalize_database_url
from scripts.verify_database import _verify_postgresql_rls


def test_sqlite_engine_creates_parent_directory_and_enforces_foreign_keys(tmp_path):
    database_file = tmp_path / "nested" / "sigillum.db"
    engine = create_database_engine(f"sqlite:///{database_file.as_posix()}")

    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
            connection.execute(
                text(
                    "CREATE TABLE child (id INTEGER PRIMARY KEY, "
                    "parent_id INTEGER NOT NULL REFERENCES parent(id))"
                )
            )
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1

            with pytest.raises(IntegrityError):
                connection.execute(
                    text("INSERT INTO child (id, parent_id) VALUES (1, 404)")
                )
    finally:
        engine.dispose()

    assert database_file.exists()


def test_postgresql_shorthand_uses_psycopg_three_driver():
    url = normalize_database_url(
        "postgresql://sigillum:password@localhost:5432/sigillum",
    )
    assert url.drivername == "postgresql+psycopg"
    assert url.username == "sigillum"
    assert url.database == "sigillum"


def test_unknown_database_backend_fails_closed():
    with pytest.raises(ValueError, match="Unsupported database backend"):
        create_database_engine("mysql+pymysql://user:password@localhost/database")


def test_alembic_upgrade_from_empty_sqlite_database_is_repeatable(tmp_path):
    database_file = tmp_path / "migration" / "fresh.db"
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{database_file.as_posix()}",
    )

    upgrade_database(settings)
    engine = create_database_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            status = get_migration_status(connection, settings)
            assert status["status"] == "current"
            assert status["current_revision"] == status["expected_revision"]

            from sqlalchemy import inspect

            tables = set(inspect(connection).get_table_names())
            assert {
                "users",
                "submissions",
                "content_versions",
                "review_runs",
                "findings",
                "patches",
                "decisions",
                "audit_events",
            }.issubset(tables)

        upgrade_database(settings)
        with engine.connect() as connection:
            status_after_repeat = get_migration_status(connection, settings)
            assert status_after_repeat["status"] == "current"
    finally:
        engine.dispose()


def test_readiness_reports_unmigrated_database_as_pending(tmp_path):
    database_file = tmp_path / "empty.db"
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{database_file.as_posix()}",
    )
    engine = create_database_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            status = get_migration_status(connection, settings)
        assert status["status"] == "pending"
        assert status["current_revision"] is None
        assert status["expected_revision"]
    finally:
        engine.dispose()



def test_invalid_database_pool_configuration_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_pool_size=0)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_max_overflow=-1)


class _FakeRLSResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._scalar


class _FakeRLSConnection:
    def __init__(self, membership_policy_count=3):
        self.membership_policy_count = membership_policy_count

    def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM pg_class" in sql:
            table_names = [value for key, value in (params or {}).items() if key.startswith("table_")]
            return _FakeRLSResult([
                {"relname": name, "relrowsecurity": True, "relforcerowsecurity": True}
                for name in table_names
            ])
        if "FROM pg_policies" in sql:
            count = self.membership_policy_count if params["table"] == "memberships" else 1
            return _FakeRLSResult(scalar=count)
        raise AssertionError(f"Unexpected verifier query: {sql}")


def test_postgresql_rls_verifier_accepts_command_specific_membership_policies():
    result = _verify_postgresql_rls(_FakeRLSConnection(membership_policy_count=3))
    assert result["status"] == "enforced"
    memberships = next(item for item in result["tables"] if item["table"] == "memberships")
    assert memberships["policy_count"] == 3
    assert memberships["required_policy_count"] == 3


def test_postgresql_rls_verifier_rejects_missing_membership_policy():
    result = _verify_postgresql_rls(_FakeRLSConnection(membership_policy_count=2))
    assert result["status"] == "incomplete"
