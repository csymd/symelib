"""
DOI normalization and extraction helpers.
"""

from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import unquote

# Core DOI path after optional resolver / prefix noise.
# Spec-ish: 10.<registrant>/<suffix> with common safe characters.
_DOI_BODY = r"10\.\d{4,}/[-._;()/:A-Za-z0-9]+"

DOI_REGEX = re.compile(_DOI_BODY, re.IGNORECASE)

# Patterns that may include a scheme/prefix before the DOI body.
_PREFIXED_PATTERNS = [
    re.compile(
        rf"(?:https?://(?:dx\.)?doi\.org/|doi:\s*)({_DOI_BODY})",
        re.IGNORECASE,
    ),
    re.compile(rf"\bDOI\s*[:=]?\s*({_DOI_BODY})", re.IGNORECASE),
    re.compile(rf"\b({_DOI_BODY})", re.IGNORECASE),
]

# Trailing junk often stuck to DOI matches in PDF text.
_TRAILING_PUNCT = re.compile(r"[.,;:]+$")


def normalize_doi(value: str | None) -> str | None:
    """
    Normalize a DOI string to canonical form: ``10.xxxx/yyyy``.

    Strips resolver URLs, ``doi:`` prefixes, whitespace, and trailing punctuation.
    Returns None if the value cannot be normalized to a plausible DOI.
    """
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None

    # Strip common wrappers
    raw = raw.replace("\u200b", "")  # zero-width space
    lower = raw.lower()
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi.org/",
        "doi:",
        "doi ",
    ):
        if lower.startswith(prefix):
            raw = raw[len(prefix) :].strip()
            lower = raw.lower()
            break

    raw = raw.strip().strip("<>[](){}")
    raw = _TRAILING_PUNCT.sub("", raw)

    match = DOI_REGEX.search(raw)
    if not match:
        return None

    doi = match.group(0)
    doi = _TRAILING_PUNCT.sub("", doi)
    # Canonical form is lowercase registrant; suffix case is significant for some
    # DOIs, but Crossref/PubMed accept lowercase — keep as found except strip noise.
    return doi


def extract_doi_from_text(text: str | None) -> str | None:
    """Find and normalize the first DOI-like token in free text."""
    if not text:
        return None
    for pattern in _PREFIXED_PATTERNS:
        match = pattern.search(text)
        if match:
            # group(1) when prefixed pattern has a capture; else group(0)
            candidate = match.group(1) if match.lastindex else match.group(0)
            normalized = normalize_doi(candidate)
            if normalized:
                return normalized
    return None


def extract_pmid_from_text(text: str | None) -> str | None:
    """Find a PubMed ID mentioned as ``PMID: 12345678`` (or similar) in text."""
    if not text:
        return None
    match = re.search(r"\bPMID\s*[:#]?\s*(\d{5,9})\b", text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"\bPubMed\s*(?:ID)?\s*[:#]?\s*(\d{5,9})\b", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _plausible_pmid(s: str) -> str | None:
    """Filter out Ovid-style article keys (00000542-…) masquerading as PMIDs."""
    if not s or not s.isdigit():
        return None
    if not (5 <= len(s) <= 9):
        return None
    # Heavy leading zeros → publisher accession keys, not PMIDs
    if s.startswith("000"):
        return None
    if int(s) < 1000:
        return None
    return s


def extract_pmid_from_filename(name: str | Path | None) -> str | None:
    """
    Pull a PMID out of common download/export filenames / titles.

    Examples seen in ~/elibrary/cart:
      ``[15432688 - Journal of Applied Bio.pdf``
      ``%5B15432688%20-%20Journal...pdf``  (URL-encoded)
      ``Unknown_NODATE_5B154326882020Journal…``  (encoded remnant after rename)
    """
    if not name:
        return None
    s = str(name)
    # Try both raw and URL-decoded forms (basename when path-like)
    candidates = [s, unquote(s), Path(s).name, Path(unquote(s)).name]
    for raw in candidates:
        # [12345678 - Title  or  (12345678 -
        m = re.search(r"[\[\(]\s*(\d{5,9})\s*[-–—:]", raw)
        if m:
            hit = _plausible_pmid(m.group(1))
            if hit:
                return hit
        # URL-encoded bracket remnant: 5B15432688… (often followed by more digits)
        m = re.search(r"5[Bb](\d{7,8})", raw)
        if m:
            hit = _plausible_pmid(m.group(1))
            if hit:
                return hit
        # %5B15432688 still fully encoded
        m = re.search(r"%5[Bb](\d{5,9})", raw, re.IGNORECASE)
        if m:
            hit = _plausible_pmid(m.group(1))
            if hit:
                return hit
        m = re.search(r"^(\d{5,9})\s*[-_]", raw)
        if m:
            hit = _plausible_pmid(m.group(1))
            if hit:
                return hit
    return None


def extract_identifiers_from_path(path: str | Path | None) -> tuple[str | None, str | None]:
    """Return (doi, pmid) hints from a filesystem path / filename only."""
    if not path:
        return None, None
    name = unquote(str(path))
    doi = extract_doi_from_text(name)
    pmid = extract_pmid_from_filename(name)
    return doi, pmid
