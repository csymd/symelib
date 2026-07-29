"""
Named paper lists (grants, manuscripts, reading projects).
"""

from datetime import datetime

from pydantic import BaseModel, Field

from elib.models.metadata import DocumentMetadata


class PaperList(BaseModel):
    """A named collection of papers (e.g. a grant or manuscript project)."""

    id: int | None = None
    name: str
    description: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    deleted_at: datetime | None = None  # soft-delete marker
    item_count: int = 0

    class Config:
        from_attributes = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class PaperListItem(BaseModel):
    """Membership of a document in a paper list."""

    list_id: int
    document_id: int
    notes: str | None = None
    added_at: datetime = Field(default_factory=datetime.now)
    document: DocumentMetadata | None = None

    class Config:
        from_attributes = True
