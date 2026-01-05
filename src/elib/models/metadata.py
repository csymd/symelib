"""
src/elib/models/metadata.py
"""
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from pydantic import BaseModel, Field

# ========================================================= #
# Document Metadata Models                                  #
# ========================================================= #

class DocumentMetadata(BaseModel):
    """Document metadata for database storage"""
    id: Optional[int] = None
    file_path: str
    filename: str
    doi: str
    pmid: Optional[str] = None
    title: str
    authors_json: str  # JSON string of authors list
    journal: str
    publication_year: Optional[int] = None
    abstract: Optional[str] = None
    keywords_json: str = "[]"  # JSON string of keywords
    file_size: int
    added_date: datetime = Field(default_factory=datetime.now)
    last_accessed: Optional[datetime] = None
    s3_synced: bool = False
    s3_path: Optional[str] = None
    
    class Config:
        from_attributes = True

class SearchQuery(BaseModel):
    """Search parameters for querying the library"""
    text: Optional[str] = None
    author: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    keywords: List[str] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

class SearchResult(BaseModel):
    """Search result entry"""
    metadata: DocumentMetadata
    relevance_score: float = 0.0
