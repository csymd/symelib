# Releasing elib

Release process for elib, aligned with the **SymWorx** branch model
(`develop` → `stage` → `release/vX.Y.Z` → `main` + tag `vX.Y.Z`),
adapted for a **single Python package** (`pyproject.toml` version).

See also: [PUBLIC_RELEASE.md](PUBLIC_RELEASE.md) (security scrub before first public push).

---

## Branch model

| Branch | Purpose |
|--------|---------|
| `develop` | Day-to-day integration. Feature PRs land here. |
| `stage` | Early-access / soak. Optional pre-releases (`0.1.0-beta.1`). |
| `release/vX.Y.Z` | Release prep only: version bump, changelog freeze, final fixes. |
| `main` | Stable releases. Tagged `vX.Y.Z` from here. |

```text
feature/* ──► develop ──► stage ──► release/vX.Y.Z ──► main
                                              │
                                              └── tag vX.Y.Z
```

**Pre-releases** (e.g. `v0.1.0-rc.1`) may be tagged from `stage` or a release branch.
**Final releases** are cut only after `release/vX.Y.Z` → `main` and tag `vX.Y.Z`.

Until `main` / `stage` exist on the remote, you can still:

1. Land work on `develop` (or finish `grok/refactor` → merge to `develop`).
2. Cut `release/v0.1.0` from the integration branch.
3. Create `main` by merging that release PR (first time).

---

## Versioning

- **SemVer** in `pyproject.toml` → `[project].version` (single source of truth).
- Git tags: `vX.Y.Z` (must match `pyproject.toml` without the leading `v`).
- Pre-release forms: `0.1.0-beta.1`, `0.1.0-rc.1` ↔ tags `v0.1.0-beta.1`, `v0.1.0-rc.1`.
- Keep a Changelog: root [`CHANGELOG.md`](../CHANGELOG.md).

Release metadata checks (when CI is enabled) should assert:

- Tag / `release/vX.Y.Z` branch version **equals** `pyproject.toml` version.
- `CHANGELOG.md` contains a `## [X.Y.Z]` section (not only `[Unreleased]`).

---

## What ships in v0.1.0 (suggested scope)

**In (core library):**

- SQLite FTS library + `elib process` / search / stats
- Metadata enrich (PubMed → Crossref → honest fallback)
- Named paper lists + BibTeX export
- Textual TUI (library, lists, PDF open via Papers/firefox)
- `elib setup`, `config.example.yaml`, local-first paths under `~/elibrary`
- Tests + pre-commit (ruff format) + CONTRIBUTING

**Out of band / clearly optional:**

- Agents / Postgres / pgvector (`compose.yaml`, `[agents]` extra) — documented, not required
- PyPI publish (optional later; start with GitHub tag + release notes)
- Full ruff lint green on entire tree (format-gated is enough for v0.1 if noted)

**Blockers before first public tag:**

- [ ] Security scrub complete ([PUBLIC_RELEASE.md](PUBLIC_RELEASE.md)) — config/example, no keys, no library PDFs
- [ ] All intentional code on `develop` (or release branch), not only a dirty working tree
- [ ] `make check` (or `pytest` + format) green
- [ ] Fresh clone smoke: `uv sync` → `elib setup` → process sample → search → TUI
- [ ] Changelog section for `0.1.0` filled in

---

## Release procedure (final `vX.Y.Z`)

### 0. Preflight (every release)

```bash
# working tree clean; on up-to-date stage (or develop if stage not used yet)
git status
make check                 # ruff format/lint checks + pytest
make pre-commit-run        # optional full-tree hooks
git grep -iE 'api_key\s*[:=].*[a-f0-9]{20}|BEGIN PRIVATE' || true
```

Confirm secrets stay in `~/.config/elib/env` / `~/elibrary/config.yaml` only.

### 1. Open the release branch

```bash
git checkout stage       # or develop if stage is not active yet
git pull
git checkout -b release/vX.Y.Z
```

### 2. Freeze version + changelog

1. Set version in `pyproject.toml`:

   ```toml
   version = "X.Y.Z"
   ```

2. In `CHANGELOG.md`:
   - Move items from `## [Unreleased]` into `## [X.Y.Z] - YYYY-MM-DD`
   - Leave a fresh empty `## [Unreleased]` section
   - Update compare links at the bottom

3. Commit:

   ```bash
   git add pyproject.toml CHANGELOG.md uv.lock   # lock if needed
   git commit -m "release: vX.Y.Z"
   git push -u origin release/vX.Y.Z
   ```

### 3. PR → `main`

- Open PR: `release/vX.Y.Z` → `main` (squash or merge commit; pick one policy and stick to it — SymWorx prefers squash for release PRs).
- Title: `release: vX.Y.Z`
- Description: short summary + checklist (tests, scrub, smoke).
- Merge only when green.

### 4. Tag

From `main` after merge:

```bash
git checkout main
git pull
git tag -a vX.Y.Z -m "elib vX.Y.Z"
git push origin main
git push origin vX.Y.Z
```

### 5. GitHub Release (manual is fine for v0.1)

- Create a GitHub Release from tag `vX.Y.Z`.
- Paste the `CHANGELOG.md` section for that version.
- Mark as pre-release if using beta/rc tags.

### 6. Back-merge (keep history linear-ish)

```bash
git checkout develop
git merge main             # or merge release branch
git push origin develop
# if using stage:
git checkout stage && git merge main && git push
```

### 7. After release

- Bump `develop` to the next **dev** intent via changelog only (version can stay until next release branch, or set `X.Y.Z+dev` only if you adopt that later — elib keeps a simple SemVer in pyproject).
- Optional: announce, update any personal notes.
- **Do not** auto-publish to PyPI until you explicitly want that (mirror SymWorx: validation first, publish jobs later).

---

## Pre-release procedure (optional)

From `stage` (or `develop`):

```bash
# e.g. 0.1.0-rc.1
# bump pyproject.toml + CHANGELOG [0.1.0-rc.1]
git tag -a v0.1.0-rc.1 -m "elib v0.1.0-rc.1"
git push origin v0.1.0-rc.1
```

GitHub Release → mark **Pre-release**.

---

## CI (when you enable Actions)

SymWorx splits **day-to-day CI** vs **release gates**. For elib (no Actions required for first tag):

| Workflow | Trigger | Checks |
|----------|---------|--------|
| `ci.yml` | PR / push `develop`, `main`, `stage`, `release/**` | `ruff format --check`, `ruff check`, `pytest` |
| `release.yml` (later) | PR → `main`, `release/**`, tags `v*` | Version ↔ tag/branch match; changelog section; full test matrix |

**Publish jobs stay disabled** until you want PyPI / automated GitHub Releases.

Local equivalent:

```bash
make check   # ruff check + format --check + pytest
```

---

## First public open-source sequence (elib today)

You are on a feature branch with substantial WIP. Recommended order:

1. **Finish scrub** (done / in progress): `config.example.yaml`, gitignore, no keys in tree, API key only in `~/.config/elib/env`.
2. **Land the product PR**: commit WIP on `grok/refactor` (or split PRs) → merge to `develop`.
3. **Create branch layout on origin** if missing:
   - `develop` = integration
   - `main` = first stable (can be created from first release)
   - optional `stage`
4. **Cut `release/v0.1.0`**, freeze changelog, smoke test.
5. **Merge to `main`**, tag `v0.1.0`, GitHub Release notes.
6. **Make repo public** only after a final `git grep` / clone smoke (see PUBLIC_RELEASE.md).
7. Add CI later; do not block v0.1 on Actions.

### Suggested first-tag version

| Choice | When |
|--------|------|
| **`0.1.0`** | Core CLI + TUI + lists usable; agents optional | **Recommended** |
| `0.1.0-rc.1` | Want external testers before “final” | Optional soak |
| `0.2.0` | Only if you want to reserve 0.1 for an older tip | Unlikely needed |

---

## PyPI (later, optional)

Not required for GitHub releases. When ready:

- Trusted publishing (OIDC) from `release.yml` on tags `v*`
- `uv build` / `uv publish` or `python -m build`
- Package name `elib` may already be taken — verify on PyPI; rename distribution if needed (`elibrary-cli`, etc.)

---

## Checklist (copy into the release PR)

- [ ] Version in `pyproject.toml` = `X.Y.Z`
- [ ] Branch name `release/vX.Y.Z` (or tag) matches
- [ ] `CHANGELOG.md` has `## [X.Y.Z] - YYYY-MM-DD`
- [ ] `make check` green
- [ ] No secrets / personal `config.yaml` / PDFs in the commit
- [ ] Smoke: setup → process → search → TUI open PDF → list export
- [ ] Tag `vX.Y.Z` on `main` after merge
- [ ] GitHub Release notes pasted from changelog
- [ ] `develop` (and `stage`) back-merged

---

## Quick reference (commands)

```bash
# cut release
git checkout -b release/v0.1.0 stage   # or develop
# edit pyproject.toml version + CHANGELOG
git commit -am "release: v0.1.0"
git push -u origin release/v0.1.0
# PR → main, merge, then:
git checkout main && git pull
git tag -a v0.1.0 -m "elib v0.1.0"
git push origin main --tags
```
