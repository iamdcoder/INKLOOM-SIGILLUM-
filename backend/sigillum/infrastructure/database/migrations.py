"""Alembic helpers used by local startup and readiness diagnostics."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from sigillum.config import Settings, get_settings
from sigillum.infrastructure.database.session import normalize_database_url

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _alembic_config(settings: Settings | None = None) -> Config:
    settings = settings or get_settings()
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    config.set_main_option(
        "sqlalchemy.url",
        normalize_database_url(settings.database_url).render_as_string(hide_password=False).replace("%", "%%"),
    )
    # env.py consumes the same validated settings object. This also allows
    # migration tests to target an isolated temporary database.
    config.attributes["sigillum_settings"] = settings
    return config


def upgrade_database(settings: Settings | None = None, revision: str = "head") -> None:
    """Apply checked-in migrations; schema creation is never done ad hoc."""
    command.upgrade(_alembic_config(settings), revision)


def get_migration_status(
    connection: Connection,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Return current and expected revisions without mutating the database."""
    config = _alembic_config(settings)
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    expected = heads[0] if len(heads) == 1 else None

    inspector = inspect(connection)
    if not inspector.has_table("alembic_version"):
        current = None
    else:
        revisions = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars().all()
        current = revisions[0] if len(revisions) == 1 else None

    current_state = "current" if expected is not None and current == expected else "pending"
    if len(heads) != 1:
        current_state = "invalid_migration_graph"

    return {
        "status": current_state,
        "current_revision": current,
        "expected_revision": expected,
        "heads": heads,
    }
