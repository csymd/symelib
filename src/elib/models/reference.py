"""
src/elib/models/reference.py
"""
from typing import Optional, List
from datetime import date

from pydantic import BaseModel, Field

# ======================================================== #
# NCBI Reference Metadata Models                           #
# ======================================================== #

class Author(BaseModel):
    """Author information"""
    last_name: str
    first_name: Optional[str] = None
    initials: Optional[str] = None
    affiliation: Optional[str] = None
    
    def format_citation(self) -> str:
        """Format for citation: LastName FM"""
        if self.initials:
            return f"{self.last_name} {self.initials}"
        return self.last_name

class Journal(BaseModel):
    """Journal information"""
    title: str
    abbreviation: Optional[str] = None
    issn: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    
class Reference(BaseModel):
    """Complete reference metadata from NCBI"""
    pmid: str
    doi: str
    title: str
    authors: List[Author] = Field(default_factory=list)
    journal: Journal
    publication_date: Optional[date] = None
    abstract: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    mesh_terms: List[str] = Field(default_factory=list)
    
    def first_author_lastname(self) -> str:
        """Get first author's last name for filename"""
        if self.authors:
            return self.authors[0].last_name
        return "Unknown"
    
    def publication_year(self) -> str:
        """Get publication year for filename"""
        if self.publication_date:
            return str(self.publication_date.year)
        return "NODATE"
    
    def generate_filename(self) -> str:
        """Generate standardized filename: FirstAuthor_Year_ShortTitle.pdf"""
        author = self.first_author_lastname()
        year = self.publication_year()
        # Clean title: take first 50 chars, remove special chars
        title_words = self.title.split()[:5]
        short_title = "_".join(title_words)
        # Remove special characters
        short_title = "".join(c for c in short_title if c.isalnum() or c in "_ ")
        short_title = short_title.replace(" ", "_")
        
        return f"{author}_{year}_{short_title}.pdf"
