"""
Build SQLite FTS5 MATCH expressions with prefix matching.

Default behavior uses token prefixes (``cardio*``) so short queries match
longer words like ``cardiovascular``. Explicit boolean queries and quoted
phrases are preserved.
"""

from __future__ import annotations

import re

from symworx_elibrary.models.metadata import SearchField

# FTS column names in documents_fts
_FIELD_COLUMN: dict[SearchField, str | None] = {
    SearchField.all: None,  # any column
    SearchField.title: "title",
    SearchField.abstract: "abstract",
    SearchField.keywords: "keywords_json",
    SearchField.author: "authors_json",
}

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-./]*")


def build_fts_match(text: str, field: SearchField = SearchField.all) -> str | None:
    """
    Convert user search text into an FTS5 MATCH expression.

    - Quoted phrases stay as phrases (no auto-prefix).
    - Bare tokens become ``token*`` (prefix) so cardio → cardiovascular.
    - Spaces imply AND between tokens.
    - If the user already wrote AND/OR/NOT between tokens, pass through lightly
      normalized (still prefix bare tokens that look like words).
    - Optional column prefix: ``title:token*`` when field is not ``all``.
    """
    raw = (text or "").strip()
    if not raw:
        return None

    col = _FIELD_COLUMN.get(field)
    col_prefix = f"{col}:" if col else ""

    # Explicit boolean operators (user intent) — still expand bare tokens
    upper = f" {raw.upper()} "
    if " AND " in upper or " OR " in upper or " NOT " in upper:
        return _expand_boolean_query(raw, col_prefix)

    # Pull out quoted phrases first (placeholders use non-token chars)
    phrases: list[str] = []
    remainder = raw

    def _store_phrase(m: re.Match) -> str:
        phrases.append(m.group(1))
        return " "

    remainder = re.sub(r'"([^"]+)"', _store_phrase, remainder)

    tokens = _TOKEN_RE.findall(remainder)
    parts: list[str] = []
    for t in tokens:
        # Escape FTS special chars in token body
        safe = t.replace('"', "")
        if not safe:
            continue
        # Prefix match unless token already has * or looks like a field:query
        if ":" in safe or safe.endswith("*"):
            parts.append(f"{col_prefix}{safe}" if col_prefix and ":" not in safe else safe)
        else:
            parts.append(f"{col_prefix}{safe}*")

    for phrase in phrases:
        escaped = phrase.replace('"', '""')
        parts.append(f'{col_prefix}"{escaped}"')

    if not parts:
        # Fallback: whole string as prefix of a single token
        safe = re.sub(r"[^\w\-./]+", "", raw)
        if not safe:
            return None
        return f"{col_prefix}{safe}*"

    return " ".join(parts)


def _expand_boolean_query(raw: str, col_prefix: str) -> str:
    """Expand bare tokens to prefix form inside a boolean expression."""
    # Split keeping operators
    pieces = re.split(r"(\bAND\b|\bOR\b|\bNOT\b|\(|\))", raw, flags=re.IGNORECASE)
    out: list[str] = []
    for piece in pieces:
        if piece is None or piece == "":
            continue
        if re.fullmatch(r"AND|OR|NOT|\(|\)", piece, flags=re.IGNORECASE):
            out.append(piece.upper() if piece.isalpha() else piece)
            continue
        # Token group
        tokens = _TOKEN_RE.findall(piece)
        if not tokens:
            continue
        expanded = []
        for t in tokens:
            safe = t.replace('"', "")
            if not safe:
                continue
            if safe.endswith("*") or ":" in safe:
                expanded.append(safe)
            else:
                expanded.append(f"{col_prefix}{safe}*")
        out.append(" ".join(expanded))
    return " ".join(out)
