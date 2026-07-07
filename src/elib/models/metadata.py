"""
Metadata handling
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

# ========================================================= #
# Document Metadata Models                                  #
# ========================================================= #


class DocumentMetadata(BaseModel):
    """Document metadata for database storage"""

    id: int | None = None
    file_path: str
    filename: str
    doi: str
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

    class Config:
        from_attributes = True


class SortBy(str, Enum):
    relevance = "relevance"
    year = "year"
    title = "title"
    added_date = "added_date"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class SearchQuery(BaseModel):
    text: str | None = None
    author: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    keywords: list[str] = Field(default_factory=list)
    doi: str | None = None
    pmid: str | None = None
    journal: str | None = None
    sort_by: SortBy = SortBy.relevance
    sort_order: SortOrder = SortOrder.desc
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class SearchResult(BaseModel):
    """Search result entry"""

    metadata: DocumentMetadata
    relevance_score: float = 0.0
