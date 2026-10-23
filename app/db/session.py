"""
Database Engine and Session Management.

Provides SQLite connection, declarative base, and session factory.
Supports file-based SQLite and in-memory SQLite (for isolated unit tests).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Default SQLite database path in data/ct200.db
DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "ct200.db"
DEFAULT_DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

Base = declarative_base()


def get_engine(database_url: str = DEFAULT_DATABASE_URL):
    """Creates a SQLAlchemy engine. Enables SQLite foreign key enforcement."""
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(
        database_url,
        echo=False,
        connect_args=connect_args,
    )

    # Enable SQLite foreign keys on connect
    if database_url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_session_factory(engine=None):
    """Returns a sessionmaker bound to the given or default engine."""
    if engine is None:
        engine = get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(engine=None) -> None:
    """Initializes all database tables registered with Base."""
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(bind=engine)


def get_db(database_url: str = DEFAULT_DATABASE_URL) -> Generator[Session, None, None]:
    """Dependency helper yielding a database session."""
    engine = get_engine(database_url)
    session_factory = get_session_factory(engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
