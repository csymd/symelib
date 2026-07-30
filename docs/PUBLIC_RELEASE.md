# Making elib public — security & safety scope

Checklist for publishing this repository without leaking personal or sensitive data, and without unsafe defaults for strangers who clone it.

**Status:** scope document (not all items implemented yet).
**Date:** 2026-07-29

---

## Goals

1. Repo can be public on GitHub without secrets or private paths.
2. New users can install, configure, and run core flows safely.
3. Optional agents/Postgres path is clearly marked and safe-by-default.
4. No accidental commit of `~/elibrary` data, API keys, or machine-local config.

---

## P0 — Must do before `git push --public` / open-sourcing

### Secrets & identity

| Item | Action | Done? |
|------|--------|-------|
| NCBI API key | Never commit. Live only in `~/.config/elib/env` (mode 600) or user-local config **outside** the git tree. | ✅ pattern |
| Rotate key | If key was ever in chat/logs/history, regenerate at NCBI account settings. | ☐ user action |
| Tracked `config.yaml` | Replace with **`config.example.yaml`** (placeholders only). **Gitignore** `config.yaml`. | ✅ |
| Personal email in git | Remove real addresses from tracked files; use `you@example.com` in examples. | ✅ tip scrubbed; history may still have old email |
| History scrub | If secrets were ever committed, use `git filter-repo` / BFG **before** first public push (rewriting after others clone is painful). | ☐ if needed |
| `~/.config/elib/env` | Confirm **not** under the repo; never add to git. | ✅ |
| S3 / bucket names | Genericize or document as “your bucket”; avoid implying private AWS account layout if sensitive. | ✅ no default bucket |

### Git hygiene

| Item | Action | Done? |
|------|--------|-------|
| `.gitignore` | Add: `config.yaml`, `.env`, `.env.*`, `data/`, `*.db`, `*.db-*`, `exports/`, `examples/output/`, maybe `library/` | ✅ |
| Example config | Commit `config.example.yaml` with all keys documented, no real secrets | ✅ |
| Setup docs | Point README/QUICKSTART at `elib setup` / `make setup` | partial |
| License | Confirm LICENSE file is intentional for public use | ✅ Apache-2.0 |
| No private PDFs | Ensure no paper PDFs or `elibrary` data are tracked | ✅ |

### Defaults that surprise the public

| Item | Action | Done? |
|------|--------|-------|
| Postgres compose | Document “dev only”; prefer `127.0.0.1:5432` bind; weak `elib:elib` password only for local demo | ✅ `compose.yaml` |
| Agents path | Keep clearly optional; no auto-start of containers on install | ☐ |
| Rate limits | Document `--delay` / API key; no aggressive default that hammers NCBI | ☐ |

### Privacy of sample content

| Item | Action | Done? |
|------|--------|-------|
| QUICKSTART / README paths | Use `$HOME/elibrary` generically, not host-specific absolute paths in docs if any remain | ☐ |
| Commit messages | Scan for emails, keys, hostnames | ☐ |

---

## P1 — Should do soon after public

| Item | Why |
|------|-----|
| Dependabot / renovate | Keep requests, textual, etc. patched |
| CI: ruff + pytest on PR | Signal quality; catch regressions |
| `SECURITY.md` | How to report issues |
| CONTRIBUTING.md | Setup + test commands | ✅ (repo root) |
| Bisync warning in docs | SQLite + multi-machine sync risks |
| PDF viewer allowlist (optional) | Reduce risk if config is attacker-writable |

---

## P2 — Nice to have

| Item | Why |
|------|-----|
| Pre-commit hooks (ruff format/lint) | ✅ local hooks; secret scan still optional |
| Container non-root docs | Agents path hardening |
| Signed releases | Tag integrity |

---

## Explicit non-goals for “public v1”

- Multi-tenant auth / multi-user server
- Encrypting the SQLite DB at rest (user’s disk encryption is enough for local-first)
- Removing NCBI email requirement (NCBI policy)

---

## Concrete file plan (when implementing P0)

```
.gitignore              # + config.yaml, .env*, *.db, data/
config.example.yaml     # placeholders
config.yaml             # untracked local only (or deleted from tracking)
README.md               # clone → make setup → process sample
docs/PUBLIC_RELEASE.md  # this checklist
SECURITY.md             # short advisory
```

Commands after scrubbing:

```bash
# verify no secrets
git grep -i 'api_key\|AKIA\|BEGIN PRIVATE' || true
gitleaks detect  # if installed

# first public remote
git remote add origin git@github.com:YOU/elib.git
git push -u origin main
```

---

## Residual risks (accept or document)

1. **User’s own `~/elibrary`** may still hold keys if they put them in bisynced `config.yaml` — document “prefer env file.”
2. **Local PDF open** runs configured viewer — trust local config.
3. **NCBI/Crossref** usage is user’s responsibility for rate limits and ToS.
4. **Paper copyright** — elib manages local PDFs; users must own rights to their library.

---

## Sign-off

Before marking public:

- [ ] P0 table complete
- [ ] Clean clone on a fresh machine: `uv sync` → `elib setup` → process a sample PDF → search → TUI
- [ ] No personal email/key in `git ls-files` content
- [ ] CI green (if enabled)
