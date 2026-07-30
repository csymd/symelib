# elib

A local paper (PDF) management system with PubMed/NCBI integration and foundations for agentic workflows.

## Features
- PDF ingestion and processing (PyPDF2; optional GROBID client)
- Metadata sourcing: **PubMed primary → Crossref fallback → honest local**
- Metadata quality tracking (`complete` / `partial` / `fallback` / `pending`)
- Search (SQLite FTS5 + metadata filters)
- Re-enrich incomplete records (`elib enrich`, `elib check-metadata`)
- Optional agents/RAG path via Postgres + pgvector

## Quick Start

Core functionality (PDF processing, search, FTS) with SQLite.

### Core usage (directory import / processing)

Your digital library will live at **`~/elibrary`** (`cart/`, `texts/`, plus `library/`, `data/`).
See **[QUICKSTART.md](QUICKSTART.md)** for the full local layout + PATH fix.

```bash
# 1. Install CLI onto PATH
cd /path/to/elib
uv tool install --force --editable .
export PATH="$HOME/.local/bin:$PATH"   # add to ~/.bashrc if needed

# 2. Config: elib setup  →  ~/elibrary/config.yaml (see config.example.yaml)

# 3. Process inbox cart → library (start small — cart is large)
elib process --limit 20
# or: elib process ~/elibrary/cart --limit 50

# 4. Search / audit / TUI / lists
elib search "CRISPR oncology"
elib check-metadata
elib enrich
elib stats
elib list create "R01-2026" -d "Grant lit"
elib tui
elib list export "R01-2026"   # → ~/elibrary/exports/
```

For the **full quickstart** (including optional agents/RAG with Postgres + pgvector + Ollama) plus Silverblue/toolbox/podman notes, see **[QUICKSTART.md](QUICKSTART.md)**.

### One-liner for the agents DB (Postgres + pgvector only)
```bash
make db-up
# (or: podman compose -f compose.yaml up -d postgres)
```

See [AGENTS.md](AGENTS.md) for the longer-term agentic vision, [CONTRIBUTING.md](CONTRIBUTING.md) for how to develop and open PRs, and [docs/RELEASING.md](docs/RELEASING.md) for release branching/tags (SymWorx-style).
