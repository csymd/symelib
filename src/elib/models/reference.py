"""
Reference models and data handling
"""

from datetime import date

from pydantic import BaseModel, Field

# ======================================================== #
# NCBI Reference Metadata Models                           #
# ======================================================== #


class Author(BaseModel):
    """Author information"""

    last_name: str
    first_name: str | None = None
    initials: str | None = None
    affiliation: str | None = None

    def format_citation(self) -> str:
        """Format for citation: LastName FM"""
        if self.initials:
            return f"{self.last_name} {self.initials}"
        return self.last_name


class Journal(BaseModel):
    """Journal information"""

    title: str
    abbreviation: str | None = None
    issn: str | None = None
    volume: str | None = None
    issue: str | None = None


class Reference(BaseModel):
    """Complete reference metadata from NCBI"""

    pmid: str
    doi: str
    title: str
    authors: list[Author] = Field(default_factory=list)
    journal: Journal
    publication_date: date | None = None
    abstract: str | None = None
    keywords: list[str] = Field(default_factory=list)
    mesh_terms: list[str] = Field(default_factory=list)

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
        short_title = "".join(c for c in short_title if c.isalnum() or c in "_")
        short_title = short_title.replace(" ", "_")

        return f"{author}_{year}_{short_title}.pdf"
