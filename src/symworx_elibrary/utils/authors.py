"""
Human-editable author lists and publication-year checks.

Editable string form (semicolon-separated):

    Last, First; Last2, First2
    Smith, Ada; Jones, Bob

A name without a comma is treated as last name only.
"""

from __future__ import annotations

import json

from symworx_elibrary.models.reference import Author

PUBLICATION_YEAR_MIN = 1000
PUBLICATION_YEAR_MAX = 2100


def validate_publication_year(year: int) -> int:
    """Return year if it is a plausible publication year; else raise ValueError."""
    if year < PUBLICATION_YEAR_MIN or year > PUBLICATION_YEAR_MAX:
        raise ValueError(
            f"Year must be between {PUBLICATION_YEAR_MIN} and {PUBLICATION_YEAR_MAX} (got {year})"
        )
    return year


def authors_from_json(authors_json: str | None) -> list[Author]:
    """Load Author records from documents.authors_json (best-effort)."""
    if not authors_json or authors_json in ("[]", "null"):
        return []
    try:
        data = json.loads(authors_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    authors: list[Author] = []
    for item in data:
        if isinstance(item, dict):
            last = (item.get("last_name") or item.get("family") or "").strip()
            if not last:
                continue
            first = item.get("first_name") or item.get("given")
            first = first.strip() if isinstance(first, str) and first.strip() else None
            initials = item.get("initials")
            initials = initials.strip() if isinstance(initials, str) and initials.strip() else None
            authors.append(Author(last_name=last, first_name=first, initials=initials))
        elif isinstance(item, str) and item.strip():
            authors.append(Author(last_name=item.strip()))
    return authors


def format_authors_editable(authors: list[Author] | str | None) -> str:
    """Format authors for an edit box: ``Last, First; Last2, First2``."""
    if isinstance(authors, str) or authors is None:
        records = authors_from_json(authors)
    else:
        records = authors
    parts: list[str] = []
    for author in records:
        last = (author.last_name or "").strip()
        if not last:
            continue
        first = (author.first_name or "").strip()
        parts.append(f"{last}, {first}" if first else last)
    return "; ".join(parts)


def parse_authors_editable(text: str) -> list[Author]:
    """Parse the editable author string into Author records.

    Raises ValueError if nothing usable is present.
    """
    raw = (text or "").strip()
    if not raw:
        raise ValueError("At least one author is required")

    authors: list[Author] = []
    for part in raw.split(";"):
        chunk = part.strip()
        if not chunk:
            continue
        if "," in chunk:
            last, rest = chunk.split(",", 1)
            last = last.strip()
            first = rest.strip() or None
        else:
            last = chunk
            first = None
        if not last:
            continue
        initials = None
        if first:
            initials = "".join(part[0] for part in first.split() if part) or None
        authors.append(Author(last_name=last, first_name=first, initials=initials))

    if not authors:
        raise ValueError("At least one author is required")
    return authors
