# elib Refactor Plan — DB / Compose / Agents Quickstart Stabilization

**Branch:** grok/refactor  
**Context:** User recently did a full podman image + toolbox container rebuild (clean slate for containers/volumes). Silverblue Fedora host with toolbox for dev work. Ollama available on the OS root via the `ollama` command.  
**Date:** 2026-07-06  
**Status:** Phase 0 + Phase 1 + rebuild/embeddings + docs largely complete. Small fixes applied during review (table names, Ollama `base_url` support for toolbox). Core paths solid. See "Current Status" below.  
**Goal:** Make `make db-up`, the Quickstart, and the documented agentic path actually executable without lying about current state. Keep agents as a true *optional modular layer* (per AGENTS.md).

## Current Reality (Diagnosis)

- **Core app is SQLite-only today**:
  - `DatabaseManager` (src/elib/services/db_manager.py) uses `sqlite3` directly.
  - `config.yaml` → `data/elib.db`.
  - All main CLI paths (`process`, `search`, `stats`, FTS `rebuild-index`) use it.
- **Postgres + pgvector is only for the agents/RAG layer** (optional extras):
  - `pyproject.toml`: `[db]` pulls sqlalchemy, alembic, psycopg, pgvector.
  - `agents` extra pulls LlamaIndex bits that target PGVectorStore.
  - `src/elib/agents/index.py` hard-assumes a running PG + a non-existent `elib.db.engine`.
- **(Historical — resolved in this pass)** Broken / incomplete pieces that were fixed:
  - Missing `compose.yml`, missing `src/elib/db/engine.py`, non-existent migrations dir, `alembic.ini` pointing at nothing.
  - `Makefile` targets and `QUICKSTART.md` were lying about the agents path.
  - `rebuild-index` had no `--embeddings` support.
  - Agents code assumed PG engine that didn't exist.
  - No toolbox / podman reset guidance.

- **Podman note**: Fresh rebuild means no pre-existing volumes, images, or containers. Compose must be (and now is) self-documenting and pull cleanly.

## Guiding Principles (from AGENTS.md + current code)

- Local-first, privacy-focused.
- Agents/RAG as **optional layer** — core paper ingestion + search must continue to work without Postgres.
- Modular: don't force sqlalchemy on people who just want `elib process` + `elib search`.
- Podman-compatible (user is on podman + toolbox likely).

## Current Status (as of 2026-07-06)

**Completed:**
- `compose.yml` + hardened Makefile with clear agents-only messaging.
- `QUICKSTART.md` rewritten with distinct Core vs Full paths + detailed Silverblue/toolbox workflow.
- `src/elib/db/engine.py` + full Alembic setup (`0001_initial_vector_store` creates pgvector + `data_document_nodes`).
- `rebuild-index --embeddings` + `--reset`, smart DOI-based updates, PDF text extraction + chunking, `populate_embeddings`/`clear_embeddings`/`get_node_count`.
- `elib agent` command with chunk count reporting.
- Agents extra carries db runtime deps; lazy imports everywhere.
- Ollama client now respects `OLLAMA_HOST` / `OLLAMA_BASE_URL` (required for toolbox reaching host Ollama on Silverblue).
- Table name bugs in helpers fixed (`data_document_nodes`).
- Extensive podman + "after full reset" documentation.
- Core (SQLite) flow completely unaffected and works with plain `uv sync`.

**Still open (see bottom of this doc):**
- Dual-store vs unified long-term.
- Whether to auto-embed on `process` (currently explicit `rebuild-index --embeddings`).
- Chroma as pure-local alternative (not started).

**Git note:** `compose.yml`, `REFACTOR_PLAN.md`, `src/elib/db/`, and `src/elib/migrations/` are the main new artifacts from this work (plus many supporting changes).

## Prioritized Execution Plan

### Phase 0 — Immediate Unblock (this session)
Make the error the user hit go away and the quickstart honest.

1. **Create `compose.yml`** (service name must be `postgres` to match Makefile targets).
   - Use a stable pgvector image (e.g. `pgvector/pgvector:pg17` or `ankane/pgvector`).
   - Named volume for data (`elib_pgdata`).
   - Standard local creds (can be overridden via env later).
   - Healthcheck + restart policy for good DX.
   - Comments about podman, fresh rebuilds, and how to connect.

2. **Harden Makefile**:
   - `db-up` / `db-down`: keep the podman compose invocation but add a pre-check or clear error message that tells the user what the compose is for (agents only).
   - Update help text (remove or qualify the "(needs compose.yml)").
   - Make `setup` target safer or split into `setup-core` vs `setup-full` (or document that `make setup` is the agents path).
   - Guard `db-migrate` or make it clearer it is for the PG path.

3. **Rewrite QUICKSTART.md**:
   - Two clear paths:
     - **Core (works today)**: uv sync, process PDFs, search, FTS rebuild. No Postgres.
     - **Full agents + RAG**: uv sync --all-extras, Ollama, `make db-up`, (future) embeddings population, `elib agent ...`.
   - Mention the recent podman rebuild implication (volumes will be fresh on first `db-up`).

4. **Light README fixes**:
   - Qualify the "SQLite → PostgreSQL migration in progress".
   - Align the tiny DB example or point to QUICKSTART.

### Phase 1 — Make Agents Path Runnable (when DB is up)
5. **Minimal `src/elib/db/engine.py`**:
   - Provide `get_engine()` that returns a SQLAlchemy Engine.
   - Default to the compose credentials + localhost (overridable via `DATABASE_URL`).
   - This satisfies the try/except in agents/index.py.
   - Note: importing this will transitively require the `db` extra (sqlalchemy).

6. **Make the agents extra compose-friendly**:
   - Either document that agents users should also pull the `db` extra, or add sqlalchemy/make_url deps into agents (or make agents depend on db).
   - Current agents/index.py already does `from sqlalchemy import make_url` inside the function — ensure it doesn't explode before the nice error in cli/agent.py.

7. **Stub alembic migrations** (so `make db-migrate` and `alembic` commands don't 100% explode):
   - Create `src/elib/migrations/` with a minimal `env.py` + `script.py.mako` (alembic init style, or the smallest that lets `alembic upgrade head` run without a real migration).
   - Or: make the Makefile target check for the dir and print a "migrations not yet implemented for this path" message.
   - Decision needed: do we want real SQLAlchemy models + migrations for the documents table soon, or keep SQLite as the "source of truth" and only use PG for vector nodes for now?

### Phase 2 — Consistency & DX
8. **Rebuild / embeddings command**:
   - Proper population with real PDF text + chunking (as above).
   - **Idempotent updates**: default behavior now deletes previous chunks for each paper's DOI (using `ref_doc_id`) before re-inserting. Re-running `elib rebuild-index --embeddings` after adding more papers safely refreshes the index without unbounded duplication.
   - Added `--reset` / `--clear-embeddings` flag for nuclear clear of the entire vector store before populating.
   - `elib agent` now reports the number of indexed chunks and gives helpful guidance when the vector store is empty.
   - Added `clear_embeddings()` and `get_node_count()` helpers in the agents module.

9. **Podman / toolbox / fresh rebuild notes**:
   - Add a small "After a full podman reset" section.
   - Suggest `podman compose pull` or just rely on `up`.
   - Note that inside toolbox the podman socket is usually forwarded; the current `podman compose` invocation should work.

10. **Optional but recommended**:
    - `.env.example` or comments in compose for DB URL, credentials.
    - Update AGENTS.md with "current status" vs "next" so the vision stays in sync.
    - Consider whether the long-term direction is dual-store (SQLite metadata + PG vectors) or a full move to SQLAlchemy + Alembic for everything.

## Open Decisions (need input)

- **Dual store vs unified?** For now we are treating PG as "vector store only" while metadata/FTS/search stay in SQLite. Is that acceptable short-term?
- **When do we populate the vector store?** `process` command would need to (optionally) chunk + embed + store in PG when agents extra is active. Or a separate `elib index-embeddings` step?
- **Scope of first Alembic migration?** If we stub it, should the first real migration just be "enable pgvector extension" + a `document_nodes` table, or also mirror the documents table?
- **Should `[agents]` extra implicitly pull the `db` deps?** (Currently they are separate.)
- **Chroma alternative?** AGENTS.md mentioned Chroma as a possibility for local vector store. Do we want a pure-local (no Postgres) agents path as a quicker win, or stay committed to pgvector because we already started the Postgres story?

## What "Done" Looks Like for This Plan

- Running `make db-up` on a fresh podman setup succeeds and brings up a healthy postgres+pgvector container.
- A new user following QUICKSTART can do the **core** flow end-to-end (`uv sync`, `elib process <dir>`, search, rebuild) without containers or old errors.
- A user who does the **full agents** path gets past the "missing engine", "no compose", and connection gotchas (with correct `DATABASE_URL` + `OLLAMA_HOST` on toolbox). Population + querying work once you have papers + embeddings.
- No commands in the happy path hard-crash due to missing generated files.
- Podman / Silverblue / toolbox / fresh rebuild context is well documented (including Ollama on host root).
- Quick verification steps (below) can be followed on the user's actual environment.

## Execution Order (this session and follow-ups)

Most items completed during the refactor + this review pass:

1. Create compose.yml (fix-01) — done
2. Harden Makefile + update help (fix-02) — done
3. Rewrite QUICKSTART.md for honesty (fix-03) — done (plus Ollama toolbox notes)
4. Light README alignment (fix-04) — done
5. Minimal engine.py (fix-06) — done
6. Alembic + real migration (fix-07) — done (0001 + smart env.py)
7. Rebuild command + embeddings + helpers (fix-05) — done, plus table name fixes
8. Podman / toolbox / Silverblue notes + docs (fix-08) — done extensively
9. Ollama host support for toolbox (added during review for verification)
10. Quick verification steps (this pass — see below) + plan tidy

---

## Quick Verification (for this environment)

Use these steps on Silverblue Fedora + toolbox. `ollama` lives on the OS root (host).

### Core (no containers / no extras needed)

```bash
# From inside your toolbox (where your uv + Python live)
cd /var/home/ntberry/worx/bitterbeta/elib

uv sync
# Edit config.yaml at minimum: ncbi_email

# Basic directory import / processing (the main "ingest a dir of PDFs")
# (use a real directory containing some PDFs)
elib process examples/          # or any dir with PDFs
elib search "your query"
elib rebuild-index
elib stats
```

Expect: successful processing (metadata + files copied to target_directory from config), FTS index, search results from local SQLite.

### Full agents path (after core papers exist)

On the **host** (outside toolbox):
```bash
ollama serve   # or ensure it's running
ollama pull llama3.1   # or your preferred model (match what's in agents/index.py or change it)
```

On the **host** (recommended):
```bash
cd /var/home/ntberry/worx/bitterbeta/elib
make db-up
```

Inside the **toolbox**:
```bash
cd /var/home/ntberry/worx/bitterbeta/elib
uv sync --all-extras

export DATABASE_URL="postgresql+psycopg://elib:elib@host.containers.internal:5432/elib"
export OLLAMA_HOST="http://host.containers.internal:11434"

make db-migrate
elib rebuild-index --embeddings          # after you have run `elib process` with some PDFs
elib agent "Summarize papers related to CRISPR"
```

Additional checks:
- `make help`
- `make db-down` / `make clean` (safe)
- Re-running `elib rebuild-index --embeddings` performs smart update (no unbounded duplication)
- `elib agent` reports non-zero chunk count when populated
- After `podman system reset` you can recover with `make db-up` + re-migrate + re-embed

Run the core path first. It must work with plain `uv sync`.

---

**Next step after this plan lands:** The user reviews this tidied plan + quick verification, confirms the root README situation for directory import, and decides on follow-ups (commit the artifacts, improve root README procedural example, next features per AGENTS.md, etc.).

Keep changes focused — do not gold-plate the full RAG ingestion in this pass unless explicitly requested.
