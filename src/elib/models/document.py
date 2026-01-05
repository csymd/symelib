"""
src/models/document.py
"""
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# ========================================================= #
# Document Models                                           #
# ========================================================= #

class DOI(BaseModel):
    """DOI identifier with validation"""
    value: str
    
    @field_validator('value')
    @classmethod
    def validate_doi(cls, v: str) -> str:
        # DOI pattern: 10.xxxx/xxxxx
        doi_pattern = r'^10\.\d{4,}\/[-._;()\/:A-Za-z0-9]+$'
        if not re.match(doi_pattern, v):
            raise ValueError(f"Invalid DOI format: {v}")
        return v.strip()
    
    def __str__(self) -> str:
        return self.value

class PDFDocument(BaseModel):
    """Represents a PDF document in the system"""
    file_path: Path
    original_filename: str
    file_size: int  # in bytes
    doi: Optional[DOI] = None
    extracted_text_preview: Optional[str] = Field(None, max_length=500)
    scan_date: datetime = Field(default_factory=datetime.now)
    processed: bool = False
    
    @field_validator('file_path')
    @classmethod
    def validate_pdf(cls, v: Path) -> Path:
        if not v.suffix.lower() == '.pdf':
            raise ValueError(f"File must be a PDF: {v}")
        return v
    
    class Config:
        arbitrary_types_allowed = True

class ProcessedDocument(PDFDocument):
    """Document after successful processing"""
    doi: DOI  # Required for processed docs
    new_filename: str
    pmid: Optional[str] = None
    processed: bool = True
    metadata_stored: bool = False
