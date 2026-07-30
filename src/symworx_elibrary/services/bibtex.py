"""
BibTeX export for DocumentMetadata / paper lists.
"""

from __future__ import annotations

from collections.abc import Iterable
import json
import re

from symworx_elibrary.models.metadata import DocumentMetadata, has_real_doi, has_real_pmid


def _escape_bibtex(value: str) -> str:
    """Escape characters that break BibTeX fields."""
    # Minimal escaping for braces and backslashes
    return (
        value.replace("\\", "\\textbackslash{}")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("#", "\\#")
        .replace("_", "\\_")
    )


def _parse_authors(authors_json: str) -> list[str]:
    """Return BibTeX-style author names: 'Last, First' joined later with ' and '."""
    if not authors_json or authors_json in ("[]", "null"):
        return []
    try:
        data = json.loads(authors_json)
    except json.JSONDecodeError:
        return []
    names: list[str] = []
    if not isinstance(data, list):
        return []
    for a in data:
        if isinstance(a, str):
            names.append(a)
            continue
        if not isinstance(a, dict):
            continue
        last = a.get("last_name") or a.get("family") or ""
        first = a.get("first_name") or a.get("given") or ""
        initials = a.get("initials") or ""
        if last and first:
            names.append(f"{last}, {first}")
        elif last and initials:
            names.append(f"{last}, {initials}")
        elif last:
            names.append(last)
    return names


def citation_key(meta: DocumentMetadata, used: set[str] | None = None) -> str:
    """
    Build a BibTeX citation key: FirstAuthorYearShortTitle (ASCII-safe).
    Ensures uniqueness within `used` when provided.
    """
    authors = _parse_authors(meta.authors_json)
    if authors:
        # "Last, First" → Last
        first_author = authors[0].split(",")[0].strip()
    else:
        first_author = "Unknown"
    first_author = re.sub(r"[^A-Za-z0-9]", "", first_author) or "Unknown"

    year = str(meta.publication_year) if meta.publication_year else "NODATE"
    words = re.findall(r"[A-Za-z0-9]+", meta.title or "")[:3]
    short = "".join(w.capitalize() for w in words) or "Paper"

    base = f"{first_author}{year}{short}"
    if used is None:
        return base
    key = base
    n = 2
    while key in used:
        key = f"{base}_{n}"
        n += 1
    used.add(key)
    return key


def document_to_bibtex(meta: DocumentMetadata, key: str | None = None) -> str:
    """Serialize one document as a BibTeX @article entry."""
    cite_key = key or citation_key(meta)
    fields: list[tuple[str, str]] = []

    fields.append(("title", f"{{{_escape_bibtex(meta.title)}}}"))

    authors = _parse_authors(meta.authors_json)
    if authors:
        author_str = " and ".join(_escape_bibtex(a) for a in authors)
        fields.append(("author", f"{{{author_str}}}"))

    if meta.journal:
        fields.append(("journal", f"{{{_escape_bibtex(meta.journal)}}}"))
    if meta.publication_year:
        fields.append(("year", str(meta.publication_year)))
    if has_real_doi(meta.doi):
        fields.append(("doi", f"{{{meta.doi}}}"))
    if has_real_pmid(meta.pmid):
        fields.append(("pmid", f"{{{meta.pmid}}}"))
        fields.append(("eprint", f"{{{meta.pmid}}}"))
        fields.append(("eprinttype", "{pubmed}"))
    if meta.abstract and meta.abstract.strip():
        # Keep abstracts; some styles ignore them
        abs_clean = " ".join(meta.abstract.split())
        if len(abs_clean) > 2000:
            abs_clean = abs_clean[:1997] + "..."
        fields.append(("abstract", f"{{{_escape_bibtex(abs_clean)}}}"))

    try:
        kws = json.loads(meta.keywords_json or "[]")
        if isinstance(kws, list) and kws:
            kw_str = ", ".join(str(k) for k in kws if k)
            if kw_str:
                fields.append(("keywords", f"{{{_escape_bibtex(kw_str)}}}"))
    except json.JSONDecodeError:
        pass

    body = ",\n".join(f"  {k} = {v}" for k, v in fields)
    return f"@article{{{cite_key},\n{body}\n}}\n"


def documents_to_bibtex(docs: Iterable[DocumentMetadata]) -> str:
    """Export many documents as a single .bib string with unique keys."""
    used: set[str] = set()
    parts: list[str] = []
    for doc in docs:
        key = citation_key(doc, used=used)
        parts.append(document_to_bibtex(doc, key=key))
    return "\n".join(parts)
