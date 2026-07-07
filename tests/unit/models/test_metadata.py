"""
tests/unit/models/test_metadata.py
"""

from datetime import datetime

from pydantic import ValidationError
import pytest

from elib.models.metadata import DocumentMetadata, SearchQuery, SearchResult, SortBy, SortOrder


# Test for DocumentMetadata model
def test_document_metadata_creation():
    metadata = DocumentMetadata(
        file_path="/path/to/file",
        filename="example.pdf",
        doi="10.1234/example.doi",
        title="Example Title",
        authors_json="['Author1', 'Author2']",
        journal="Example Journal",
        publication_year=2023,
        abstract="This is an example abstract.",
        keywords_json="['keyword1', 'keyword2']",
        file_size=1024,
    )
    assert metadata.file_path == "/path/to/file"
    assert metadata.filename == "example.pdf"
    assert metadata.doi == "10.1234/example.doi"
    assert metadata.authors_json == "['Author1', 'Author2']"
    assert metadata.journal == "Example Journal"
    assert metadata.publication_year == 2023
    assert metadata.abstract == "This is an example abstract."
    assert metadata.keywords_json == "['keyword1', 'keyword2']"
    assert metadata.file_size == 1024
    assert isinstance(metadata.added_date, datetime)
    assert metadata.s3_synced is False


def test_document_metadata_validation_error():
    with pytest.raises(ValidationError):
        DocumentMetadata(
            file_path="/path/to/file",
            filename="example.pdf",
            doi="10.1234/example.doi",
            title="Example Title",
            authors_json="['Author1', 'Author2']",
            journal="Example Journal",
            file_size="invalid_size",
        )


# Test for SearchQuery model
def test_search_query_defaults():
    query = SearchQuery()
    assert query.text is None
    assert query.author is None
    assert query.year_from is None
    assert query.year_to is None
    assert query.keywords == []
    assert query.doi is None
    assert query.pmid is None
    assert query.journal is None
    assert query.sort_by == SortBy.relevance
    assert query.sort_order == SortOrder.desc
    assert query.limit == 50
    assert query.offset == 0


def test_search_query_validation_error():
    with pytest.raises(ValidationError):
        SearchQuery(limit=2000)  # Limit exceeds the maximum allowed value


# Test for SearchResult model
def test_search_result_creation():
    metadata = DocumentMetadata(
        file_path="/path/to/file",
        filename="example.pdf",
        doi="10.1234/example.doi",
        title="Example Title",
        authors_json="['Author1', 'Author2']",
        journal="Example Journal",
        file_size=1024,
    )
    result = SearchResult(metadata=metadata, relevance_score=0.85)
    assert result.metadata == metadata
    assert result.relevance_score == 0.85
