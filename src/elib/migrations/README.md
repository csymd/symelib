# Alembic Migrations

This directory contains database migrations for the **optional** Postgres + pgvector
vector store used by the agents / RAG features.

The core elib functionality (PDF processing, metadata, full-text search) continues
to use the direct SQLite implementation in `services/db_manager.py`.

## Current migrations

- `0001_initial_vector_store` — Enables the `vector` extension and creates the
  `data_document_nodes` table (plus supporting index) that LlamaIndex's
  `PGVectorStore(table_name="document_nodes", embed_dim=384)` expects.

## How to run

```bash
make db-migrate
# or directly:
uv run --extra db alembic upgrade head
```

The environment tries hard to use the same connection as the rest of the app
(see `env.py` + `src/elib/db/engine.py` and the defaults from `compose.yml`).

## Notes

- `target_metadata = None` (no autogenerate yet) because we don't have
  SQLAlchemy models for the main document store.
- The agents code (`agents/index.py`) still does a best-effort
  `CREATE EXTENSION` on first use as a fallback if the migration hasn't been
  run.
- Future migrations may add a full `documents` mirror table if/when we decide
  to move away from the dual-store (SQLite + pgvector) approach.

See `REFACTOR_PLAN.md` for the broader status of the Postgres migration story.

When the README content is updated, you can leave or remove this file as desired.
