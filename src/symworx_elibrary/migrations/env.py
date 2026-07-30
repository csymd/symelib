"""
Alembic environment configuration.

This is used for the optional Postgres + pgvector vector store migrations
(agents/RAG path). The core application still uses SQLite directly.

Key points:
- target_metadata = None because we don't (yet) have SQLAlchemy declarative
  models for autogenerate on the main documents table.
- We pull the database URL from symworx_elibrary.db.engine (which respects DATABASE_URL
  env var and matches the defaults in compose.yaml) so that `alembic` commands
  and `make db-migrate` "just work" with the same connection as the rest of
  the agents code.
- First migration (0001) sets up the pgvector extension + the
  `data_document_nodes` table used by LlamaIndex PGVectorStore.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Pull the database URL from our application code so that migrations
# use the same connection details (and defaults) as the agents vector store.
# This respects the DATABASE_URL environment variable and the compose.yaml defaults.
try:
    # Ensure src is importable when running alembic directly
    from pathlib import Path
    import sys

    project_root = Path(__file__).resolve().parents[3]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    if str(project_root / "src") not in sys.path:
        sys.path.insert(0, str(project_root / "src"))

    from symworx_elibrary.db.engine import get_database_url

    url = get_database_url()
    config.set_main_option("sqlalchemy.url", url)
except Exception:
    # If we can't import (e.g. during some packaging scenarios), fall back
    # to whatever is in alembic.ini or command-line -A/--x arguments.
    pass

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = None

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = config.attributes.get("connection", None)

    if connectable is None:
        from sqlalchemy import engine_from_config
        from sqlalchemy.pool import NullPool

        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=NullPool,
        )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
