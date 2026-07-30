"""
Crossref Works API client for DOI metadata fallback.
"""

from __future__ import annotations

from datetime import date
import re
import time
from typing import Any

import requests

from symworx_elibrary.models.reference import Author, Journal, Reference
from symworx_elibrary.utils.doi_parser import normalize_doi
from symworx_elibrary.utils.logging import LoggerConfig, get_shared_logger
from symworx_elibrary.utils.rate_limiter import crossref_throttle

logger = get_shared_logger(LoggerConfig(name="crossref_client"))

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = _TAG_RE.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _parse_date_parts(message: dict[str, Any]) -> date | None:
    """Prefer issued → published-print → published-online date-parts."""
    for key in ("issued", "published-print", "published-online", "created"):
        parts = (message.get(key) or {}).get("date-parts")
        if not parts or not parts[0]:
            continue
        nums = parts[0]
        try:
            year = int(nums[0])
            month = int(nums[1]) if len(nums) > 1 else 1
            day = int(nums[2]) if len(nums) > 2 else 1
            month = max(1, min(month, 12))
            day = max(1, min(day, 28 if month == 2 else 31))
            return date(year, month, day)
        except (TypeError, ValueError):
            continue
    return None


def crossref_message_to_reference(message: dict[str, Any]) -> Reference | None:
    """Map a Crossref work `message` object to a Reference."""
    doi = normalize_doi(message.get("DOI")) or (message.get("DOI") or "")
    titles = message.get("title") or []
    title = titles[0] if titles else "No title"

    authors: list[Author] = []
    for a in message.get("author") or []:
        family = a.get("family") or a.get("name")
        if not family:
            continue
        given = a.get("given")
        initials = None
        if given:
            initials = "".join(p[0] for p in given.split() if p)
        authors.append(Author(last_name=family, first_name=given, initials=initials))

    container = message.get("container-title") or []
    short = message.get("short-container-title") or []
    journal = Journal(
        title=container[0] if container else (message.get("publisher") or "Unknown"),
        abbreviation=short[0] if short else None,
        volume=str(message["volume"]) if message.get("volume") else None,
        issue=str(message["issue"]) if message.get("issue") else None,
        issn=(message.get("ISSN") or [None])[0],
    )

    abstract = _strip_html(message.get("abstract"))
    # Crossref subjects / keywords when present
    keywords: list[str] = []
    for s in message.get("subject") or []:
        if isinstance(s, str):
            keywords.append(s)

    pub_date = _parse_date_parts(message)

    return Reference(
        pmid="",  # Crossref does not provide PMID
        doi=doi or "",
        title=title,
        authors=authors,
        journal=journal,
        publication_date=pub_date,
        abstract=abstract,
        keywords=keywords,
        mesh_terms=[],
    )


class CrossrefClient:
    """Minimal Crossref Works API client (polite pool via mailto)."""

    BASE_URL = "https://api.crossref.org"

    def __init__(self, mailto: str, session: requests.Session | None = None):
        self.mailto = mailto
        self.session = session or requests.Session()
        # Crossref polite pool
        self.session.headers.update(
            {
                "User-Agent": f"elib/0.1 (mailto:{mailto})",
            }
        )

    def fetch_by_doi(self, doi: str) -> Reference | None:
        """Fetch metadata for a DOI from Crossref. Returns None on miss/error."""
        normalized = normalize_doi(doi)
        if not normalized:
            logger.warning("Crossref fetch skipped: invalid DOI", doi=doi)
            return None

        url = f"{self.BASE_URL}/works/{normalized}"
        params = {"mailto": self.mailto}
        throttle = crossref_throttle()
        try:
            for _attempt in range(5):
                throttle.wait()
                response = self.session.get(url, params=params, timeout=30)
                if response.status_code == 429:
                    ra = response.headers.get("Retry-After")
                    sleep_s = throttle.on_rate_limit(
                        float(ra) if ra and str(ra).isdigit() else None
                    )
                    print(f"  Crossref 429 — sleeping {sleep_s:.1f}s…")
                    time.sleep(sleep_s)
                    continue
                if response.status_code == 404:
                    throttle.on_success()
                    logger.info("Crossref: DOI not found", doi=normalized)
                    return None
                response.raise_for_status()
                throttle.on_success()
                payload = response.json()
                message = payload.get("message") or {}
                ref = crossref_message_to_reference(message)
                if ref:
                    logger.info("Crossref: fetched work", doi=normalized, title=ref.title[:80])
                return ref
            return None
        except requests.RequestException as e:
            logger.error("Crossref request failed", doi=normalized, error=str(e))
            return None
