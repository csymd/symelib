# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Textual TUI: library search, detail, named paper lists, PDF open (Papers / configurable viewer).
- Metadata pipeline: PubMed primary → Crossref fallback → honest local status tracking.
- Paper lists: create, rename, soft-delete/restore, BibTeX export (`elib list`, TUI `l` / `m`).
- `elib setup` + `config.example.yaml`; library layout under `$ELIB_HOME` (cart, library, data, exports, tmp).
- Rate limiting / 429 backoff for NCBI and Crossref; optional API key via env.
- Pre-commit hooks (ruff format + import sort); CONTRIBUTING.md.
- Optional agents/RAG path (Postgres + pgvector via `compose.yaml`) — not required for core use.

### Changed
- Config defaults scrubbed for public use (no personal email/bucket in repo template).
- Compose file renamed to `compose.yaml`; Postgres bound to `127.0.0.1`.

### Security
- Prefer NCBI API key in `~/.config/elib/env` (mode 600), not in bisynced `config.yaml`.
- Tracked secrets removed from example config; `config.yaml` gitignored.

## [0.1.0] - TBD

### Added
- Initial public-oriented release of elib (local-first PDF library + PubMed integration + TUI).

### Notes
- Target first tagged release after landing the refactor branch, security scrub sign-off, and smoke test on a clean clone.
- Branching model: `develop` / `stage` / `main` with `release/vX.Y.Z` prep branches (see [docs/RELEASING.md](docs/RELEASING.md)).

---

## Version Links

[Unreleased]: https://github.com/symworx/symworx-elibrary/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/symworx/symworx-elibrary/releases/tag/v0.1.0
