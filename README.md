# elib

A local paper (PDF) management system with PubMed/NCBI integration and foundations for agentic workflows.

## Features
- PDF ingestion and processing (pdfplumber + GROBID support)
- Metadata extraction and deduplication
- Search (FTS + upcoming semantic)
- SQLite → PostgreSQL migration in progress
- Podman-compatible container setup

## Quick Start

### Database (Podman)
```bash
podman compose up -d postgres
```

### Install
```bash
uv sync
```

See `docs/` or AGENTS.md for more.

## Status
On `grok/refactor` branch: Priority 1 & 2 in progress.