"""
Minimal SQLAlchemy engine factory for the Postgres + pgvector (agents/RAG) path.

This satisfies the import that agents/index.py expects:
    from elib.db.engine import get_engine

Defaults are chosen to match the compose.yaml we ship:
    postgresql+psycopg://elib:elib@localhost:5432/elib

When running elib from inside a toolbox / distrobox container (common on
immutable Fedora hosts), "localhost" will not reach the Postgres container
running on the host. Set this instead:

    export DATABASE_URL="postgresql+psycopg://elib:elib@host.containers.internal:5432/elib"

Override with the DATABASE_URL environment variable (full SQLAlchemy URL) in
all cases. See compose.yaml and QUICKSTART.md for the full toolbox workflow.

This module requires the [db] extra (sqlalchemy + psycopg etc.).
It is intentionally NOT used by the core SQLite code paths.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def get_engine() -> Engine:
    """
    Return a SQLAlchemy Engine pointed at the Postgres instance.

    The compose.yaml + defaults are intended for local development only.
    In real deployments you would inject DATABASE_URL (e.g. from secrets or .env).
    """
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://elib:elib@localhost:5432/elib",
    )
    # Future enhancement: pool size, connect args, echo=bool(os.getenv("SQL_ECHO"))
    engine = create_engine(url, future=True)
    return engine


def get_database_url() -> str:
    """Convenience helper if callers just need the raw URL string."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://elib:elib@localhost:5432/elib",
    )
