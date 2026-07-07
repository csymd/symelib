"""
src/elib/db/

Lightweight SQLAlchemy engine access for the optional Postgres + pgvector agents path.

Core elib (ingestion, search, FTS) continues to use the direct SQLite DatabaseManager
in services/db_manager.py. This module is only imported when the [db] (and usually [agents])
extras are active.
"""
