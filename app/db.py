from datetime import UTC
from pathlib import Path

from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """SQLite stores naive UTC; Python and the API always receive aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("A timezone-aware datetime is required")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


def build_engine(database_url: str):
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("This MVP supports SQLite only")
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 5}, hide_parameters=True)

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _):
        # Use explicit transactions, including DDL, instead of sqlite3 legacy mode.
        connection.isolation_level = None
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    @event.listens_for(engine, "begin")
    def begin(connection):
        connection.exec_driver_sql("BEGIN")

    return engine


def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine):
    from app import models  # noqa: F401: register all mapped tables

    database = engine.url.database
    if database and database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    # Import canonical module so mapped classes share the same Base.
    import argparse
    from app.config import Settings
    from app.db import build_engine, init_db

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init-db"])
    parser.parse_args()
    engine = build_engine(Settings().database_url)
    init_db(engine)
    engine.dispose()
    print("Database schema initialized.")
