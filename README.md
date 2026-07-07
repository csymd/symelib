# elib

A local paper (PDF) management system with PubMed/NCBI integration and foundations for agentic workflows.

## Features
- PDF ingestion and processing (pdfplumber + GROBID support)
- Metadata extraction and deduplication
- Search (FTS + upcoming semantic)
- SQLite → PostgreSQL migration in progress
- Podman-compatible container setup

## Quick Start

Core functionality (PDF processing, search, FTS) works with SQLite today — no containers required.

### Core usage (directory import / processing)

```bash
# 1. Install
uv sync

# 2. Edit config.yaml (at minimum set your ncbi_email)
#    database_path and target_directory are also there.

# 3. Import / process a directory of PDFs (the main ingestion command)
elib process /path/to/your/pdfs
# or with a specific target dir:
# elib process /path/to/pdfs --target-dir ./my-library

# 4. Search your local library (FTS + metadata)
elib search "CRISPR oncology"

# 5. After bulk changes, rebuild the full-text index
elib rebuild-index

# Other useful commands
elib stats
```

For the **full quickstart** (including optional agents/RAG with Postgres + pgvector + Ollama) plus Silverblue/toolbox/podman notes, see **[QUICKSTART.md](QUICKSTART.md)**.

### One-liner for the agents DB (Postgres + pgvector only)
```bash
make db-up
# (or: podman compose -f compose.yml up -d postgres)
```

See [AGENTS.md](AGENTS.md) for the longer-term agentic vision and [REFACTOR_PLAN.md](REFACTOR_PLAN.md) for the current stabilization tasks on this branch.

## Status
On `grok/refactor` branch. Core paths (SQLite + `elib process <directory>`, search, FTS) are fully usable with no containers. The optional agents/RAG path (Postgres + pgvector + Ollama) is now executable end-to-end; see QUICKSTART.md for the complete procedural flow including Silverblue + toolbox details.

See REFACTOR_PLAN.md for the current state of the stabilization work.