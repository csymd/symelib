"""
Metadata handling
"""

from datetime import date, datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

# ========================================================= #
# Document Metadata Models                                  #
# ========================================================= #


class MetadataStatus(str, Enum):
    """Lifecycle quality of document metadata."""

    complete = "complete"  # Real identifier + title + authors from a remote source
    partial = "partial"  # Identifier found; some fields missing
    fallback = "fallback"  # Local-only; no successful remote enrichment
    pending = "pending"  # Queued / not yet checked


class MetadataSource(str, Enum):
    """Where metadata was last sourced from."""

    pubmed = "pubmed"
    crossref = "crossref"
    local = "local"
    manual = "manual"


class MetadataIssue(str, Enum):
    """
    Why enrichment stopped short of complete remote metadata.

    Stored so we can filter and re-run later (e.g. only scanned PDFs, or only
    PubMed misses).
    """

    none = "none"  # remote metadata ok (complete or partial with real ID)
    no_text = "no_text"  # PDF text extraction empty / near-empty (likely scan)
    no_identifier = "no_identifier"  # text ok but no DOI/PMID found
    pubmed_miss = "pubmed_miss"  # had DOI/PMID; PubMed returned nothing useful
    crossref_miss = "crossref_miss"  # had DOI; Crossref miss after PubMed miss
    remote_error = "remote_error"  # network / API / parse error talking to remote
    parse_error = "parse_error"  # local PDF processing exception
    unknown = "unknown"  # legacy / unclassified fallback


# Synthetic markers used by older elib versions — treat as no real identifier.
SYNTHETIC_DOI_PREFIX = "10.9999/"
SYNTHETIC_PMID_PREFIX = "LOCAL-"


def is_synthetic_doi(doi: str | None) -> bool:
    """Return True if DOI is missing or a historically fabricated local placeholder."""
    if not doi or not doi.strip():
        return True
    return doi.strip().lower().startswith(SYNTHETIC_DOI_PREFIX.lower())


def is_synthetic_pmid(pmid: str | None) -> bool:
    """Return True if PMID is missing or a historically fabricated local placeholder."""
    if not pmid or not pmid.strip():
        return True
    return pmid.strip().upper().startswith(SYNTHETIC_PMID_PREFIX.upper())


def has_real_doi(doi: str | None) -> bool:
    return not is_synthetic_doi(doi)


def has_real_pmid(pmid: str | None) -> bool:
    return not is_synthetic_pmid(pmid)


def classify_metadata_status(
    *,
    doi: str | None,
    pmid: str | None,
    title: str | None,
    authors_json: str | None,
    abstract: str | None,
    source: MetadataSource | str | None = None,  # noqa: ARG001 — reserved for scoring
) -> MetadataStatus:
    """Heuristically classify metadata quality for backfill / post-fetch."""
    real_id = has_real_doi(doi) or has_real_pmid(pmid)
    if not real_id:
        return MetadataStatus.fallback

    authors_ok = bool(authors_json and authors_json not in ("[]", "null", "None"))
    title_ok = bool(
        title and title.strip() and title.strip().lower() not in ("untitled document", "no title")
    )
    abstract_ok = bool(abstract and abstract.strip())

    if title_ok and authors_ok and abstract_ok:
        return MetadataStatus.complete
    if title_ok and authors_ok:
        # Remote hit with usable citation fields but no abstract is still "partial"
        return MetadataStatus.partial
    return MetadataStatus.partial


class DocumentMetadata(BaseModel):
    """Document metadata for database storage"""

    id: int | None = None
    file_path: str
    filename: str
    # Real DOI when known; empty string for local-only rows (SQLite transition:
    # historical NOT NULL column; empty string means "no real DOI").
    doi: str = ""
    pmid: str | None = None
    title: str
    authors_json: str
    journal: str
    publication_year: int | None = None
    abstract: str | None = None
    keywords_json: str = "[]"
    file_size: int
    added_date: datetime = Field(default_factory=datetime.now)
    last_accessed: datetime | None = None
    s3_synced: bool = False
    s3_path: str | None = None
    metadata_status: MetadataStatus = MetadataStatus.pending
    metadata_source: MetadataSource | None = None
    metadata_checked_at: datetime | None = None
    # Diagnostics for re-run / debug
    metadata_issue: MetadataIssue = MetadataIssue.unknown
    metadata_detail: str | None = None
    text_extract_chars: int | None = None
    source_path: str | None = None  # original inbox path (tmp/cart; dedup + reprocess)
    original_filename: str | None = None

    class Config:
        from_attributes = True

    @field_validator("metadata_status", mode="before")
    @classmethod
    def _coerce_status(cls, v):
        if v is None or v == "":
            return MetadataStatus.pending
        if isinstance(v, MetadataStatus):
            return v
        return MetadataStatus(v)

    @field_validator("metadata_source", mode="before")
    @classmethod
    def _coerce_source(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, MetadataSource):
            return v
        return MetadataSource(v)

    @field_validator("metadata_issue", mode="before")
    @classmethod
    def _coerce_issue(cls, v):
        if v is None or v == "":
            return MetadataIssue.unknown
        if isinstance(v, MetadataIssue):
            return v
        try:
            return MetadataIssue(v)
        except ValueError:
            return MetadataIssue.unknown

    def has_real_doi(self) -> bool:
        return has_real_doi(self.doi)

    def has_real_pmid(self) -> bool:
        return has_real_pmid(self.pmid)


class SortBy(str, Enum):
    relevance = "relevance"
    year = "year"
    author = "author"
    title = "title"
    added_date = "added_date"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class ImportWindow(str, Enum):
    """Relative window on documents.added_date (when the file was ingested)."""

    all = "all"
    today = "today"
    days_7 = "7d"
    days_30 = "30d"


def import_window_bounds(
    window: ImportWindow | str,
    *,
    today: date | None = None,
) -> tuple[date | None, date | None]:
    """Inclusive [from, to] calendar dates for an import-time window.

    ``all`` → ``(None, None)`` (no filter). Unknown values are treated as ``all``.
    """
    if isinstance(window, str):
        try:
            window = ImportWindow(window)
        except ValueError:
            return None, None
    day = today or date.today()
    if window == ImportWindow.today:
        return day, day
    if window == ImportWindow.days_7:
        return day - timedelta(days=6), day
    if window == ImportWindow.days_30:
        return day - timedelta(days=29), day
    return None, None


def added_date_sql_filter(
    added_from: date | None,
    added_to: date | None,
) -> tuple[str, list[str]]:
    """AND clauses + ISO date params for an inclusive import-date range.

    Compares ``date(d.added_date, 'localtime')`` so SQLite UTC
    ``CURRENT_TIMESTAMP`` values line up with local calendar days (the same
    clock ``date.today()`` uses). Empty string / no params when neither bound
    is set. Callers must already have a WHERE clause (or ``WHERE 1=1``).
    """
    clauses: list[str] = []
    params: list[str] = []
    if added_from is not None:
        clauses.append("date(d.added_date, 'localtime') >= date(?)")
        params.append(added_from.isoformat())
    if added_to is not None:
        clauses.append("date(d.added_date, 'localtime') <= date(?)")
        params.append(added_to.isoformat())
    if not clauses:
        return "", []
    return " AND " + " AND ".join(clauses), params


def sort_sql_clause(sort_by: SortBy, sort_order: SortOrder, *, use_fts: bool = False) -> str:
    """Build a safe ORDER BY clause (enum-only; never interpolates user text)."""
    order = "ASC" if sort_order == SortOrder.asc else "DESC"
    if sort_by == SortBy.relevance and use_fts:
        return " ORDER BY relevance ASC"
    if sort_by == SortBy.year:
        # NULLs last when DESC years first; when ASC, missing years last
        return (
            f" ORDER BY (d.publication_year IS NULL) ASC, d.publication_year {order}, d.title ASC"
        )
    if sort_by == SortBy.author:
        # First author's last_name from authors_json
        return (
            " ORDER BY (json_extract(d.authors_json, '$[0].last_name') IS NULL) ASC, "
            f"json_extract(d.authors_json, '$[0].last_name') COLLATE NOCASE {order}, "
            "d.title COLLATE NOCASE ASC"
        )
    if sort_by == SortBy.title:
        return f" ORDER BY d.title COLLATE NOCASE {order}"
    # added_date default
    return f" ORDER BY d.added_date {order}"


class SearchField(str, Enum):
    """Which bibliographic fields text search targets.

    ``all`` (default): title + abstract + keywords + authors via FTS, with
    prefix matching so ``cardio`` matches ``cardiovascular``.
    """

    all = "all"
    title = "title"
    keywords = "keywords"
    author = "author"
    abstract = "abstract"


class SearchQuery(BaseModel):
    text: str | None = None
    author: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    keywords: list[str] = Field(default_factory=list)
    doi: str | None = None
    pmid: str | None = None
    journal: str | None = None
    metadata_status: MetadataStatus | None = None
    # Inclusive calendar-day bounds on documents.added_date (ingest time)
    added_from: date | None = None
    added_to: date | None = None
    # Where free-text ``text`` is applied (title/keywords/author/abstract/all)
    search_field: SearchField = SearchField.all
    sort_by: SortBy = SortBy.relevance
    sort_order: SortOrder = SortOrder.desc
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _added_range_order(self):
        if (
            self.added_from is not None
            and self.added_to is not None
            and self.added_from > self.added_to
        ):
            raise ValueError("added_from must be on or before added_to")
        return self


class SearchResult(BaseModel):
    """Search result entry"""

    metadata: DocumentMetadata
    relevance_score: float = 0.0
