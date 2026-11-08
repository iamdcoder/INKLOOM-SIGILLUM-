"""Database engine and session configuration.

SQLite is the local development/test default. PostgreSQL uses psycopg 3 with
bounded connection/pool settings and pre-ping so stale pooled connections are
replaced before use.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from sigillum.config import get_settings


def normalize_database_url(database_url: str | URL) -> URL:
    """Normalise the PostgreSQL shorthand to the pinned psycopg 3 driver."""
    url = make_url(database_url) if isinstance(database_url, str) else database_url
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url


def create_database_engine(
    database_url: str | URL,
    *,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_timeout_seconds: int = 30,
    connect_timeout_seconds: int = 5,
) -> Engine:
    """Build a supported SQLAlchemy engine with safe, explicit defaults."""
    url = normalize_database_url(database_url)
    backend = url.get_backend_name()

    if backend == "sqlite":
        database = url.database
        if database and database not in {":memory:"} and not database.startswith("file:"):
            Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

        engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30},
            pool_pre_ping=True,
        )

        @event.listens_for(engine, "connect")
        def _configure_sqlite(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
            finally:
                cursor.close()

        return engine

    if backend == "postgresql":
        return create_engine(
            url,
            connect_args={
                "connect_timeout": connect_timeout_seconds,
                "application_name": "inkloom-sigillum",
            },
            pool_pre_ping=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout_seconds,
            pool_recycle=1800,
        )

    raise ValueError(
        f"Unsupported database backend '{backend}'. "
        "Use SQLite for local development or PostgreSQL with psycopg 3."
    )


settings = get_settings()
engine = create_database_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout_seconds=settings.database_pool_timeout_seconds,
    connect_timeout_seconds=settings.database_connect_timeout_seconds,
)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


@event.listens_for(Session, "after_begin")
def _apply_postgresql_row_scope(session: Session, _transaction, connection) -> None:
    """Reapply transaction-local RLS context after every commit/rollback boundary.

    The API dependency sets this context only after validating the signed token and
    loading the matching active membership. Worker/service code must set an
    explicit context before accessing tenant-scoped tables.
    """
    if connection.dialect.name != "postgresql":
        return
    scope = session.info.get("rls_context")
    if not scope:
        return
    values = {
        "app.user_id": scope.get("user_id", ""),
        "app.tenant_id": scope.get("tenant_id", ""),
        "app.brand_id": scope.get("brand_id", ""),
        "app.brand_record_id": scope.get("brand_record_id", ""),
        "app.membership_role": scope.get("membership_role", ""),
    }
    for key, value in values.items():
        connection.execute(
            text("SELECT set_config(:setting_name, :setting_value, true)"),
            {"setting_name": key, "setting_value": str(value or "")},
        )


def set_database_scope(session: Session, **scope: str) -> None:
    """Set the trusted request scope and apply it to the current PG transaction."""
    session.info["rls_context"] = scope
    if session.get_bind().dialect.name != "postgresql":
        return
    connection = session.connection()
    for key, value in {
        "app.user_id": scope.get("user_id", ""),
        "app.tenant_id": scope.get("tenant_id", ""),
        "app.brand_id": scope.get("brand_id", ""),
        "app.brand_record_id": scope.get("brand_record_id", ""),
        "app.membership_role": scope.get("membership_role", ""),
    }.items():
        connection.execute(
            text("SELECT set_config(:setting_name, :setting_value, true)"),
            {"setting_name": key, "setting_value": str(value or "")},
        )


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
