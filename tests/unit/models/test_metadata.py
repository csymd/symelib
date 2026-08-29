"""
tests/unit/models/test_metadata.py
"""

from datetime import date, datetime, timedelta

from pydantic import ValidationError
import pytest

from symworx_elibrary.models.metadata import (
    DocumentMetadata,
    ImportWindow,
    MetadataSource,
    MetadataStatus,
    SearchQuery,
    SearchResult,
    SortBy,
    SortOrder,
    added_date_sql_filter,
    classify_metadata_status,
    has_real_doi,
    has_real_pmid,
    import_window_bounds,
    is_synthetic_doi,
    is_synthetic_pmid,
)


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
    assert metadata.metadata_status == MetadataStatus.pending
    assert metadata.metadata_source is None


def test_document_metadata_with_status():
    metadata = DocumentMetadata(
        file_path="/path/to/file",
        filename="example.pdf",
        doi="10.1234/example.doi",
        title="Example Title",
        authors_json='[{"last_name": "Doe"}]',
        journal="Example Journal",
        file_size=1024,
        metadata_status=MetadataStatus.complete,
        metadata_source=MetadataSource.pubmed,
    )
    assert metadata.metadata_status == MetadataStatus.complete
    assert metadata.metadata_source == MetadataSource.pubmed
    assert metadata.has_real_doi() is True


def test_document_metadata_empty_doi_default():
    metadata = DocumentMetadata(
        file_path="/path/to/file",
        filename="local.pdf",
        title="Local Only",
        authors_json="[]",
        journal="Local",
        file_size=100,
        metadata_status=MetadataStatus.fallback,
        metadata_source=MetadataSource.local,
    )
    assert metadata.doi == ""
    assert metadata.has_real_doi() is False


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


def test_synthetic_helpers():
    assert is_synthetic_doi(None)
    assert is_synthetic_doi("")
    assert is_synthetic_doi("10.9999/elib-local-123")
    assert not is_synthetic_doi("10.1234/real.doi")
    assert has_real_doi("10.1234/real.doi")
    assert not has_real_doi("10.9999/elib-local-123")

    assert is_synthetic_pmid(None)
    assert is_synthetic_pmid("LOCAL-12345")
    assert not is_synthetic_pmid("12345678")
    assert has_real_pmid("12345678")
    assert not has_real_pmid("LOCAL-1")


def test_classify_metadata_status():
    assert (
        classify_metadata_status(
            doi="",
            pmid=None,
            title="Something",
            authors_json="[]",
            abstract=None,
        )
        == MetadataStatus.fallback
    )
    assert (
        classify_metadata_status(
            doi="10.9999/elib-local-1",
            pmid="LOCAL-1",
            title="Something",
            authors_json="[]",
            abstract="preview",
        )
        == MetadataStatus.fallback
    )
    assert (
        classify_metadata_status(
            doi="10.1234/x",
            pmid="1",
            title="A real title",
            authors_json='[{"last_name": "Doe"}]',
            abstract="Full abstract text.",
        )
        == MetadataStatus.complete
    )
    assert (
        classify_metadata_status(
            doi="10.1234/x",
            pmid="1",
            title="A real title",
            authors_json='[{"last_name": "Doe"}]',
            abstract=None,
        )
        == MetadataStatus.partial
    )


# Test for SearchQuery model
def test_search_query_defaults():
    query = SearchQuery()
    assert query.text is None
    assert query.author is None
    assert query.year_from is None
    assert query.year_to is None
    assert query.added_from is None
    assert query.added_to is None
    assert query.keywords == []
    assert query.doi is None
    assert query.pmid is None
    assert query.journal is None
    assert query.metadata_status is None
    assert query.sort_by == SortBy.relevance
    assert query.sort_order == SortOrder.desc
    assert query.limit == 50
    assert query.offset == 0


def test_search_query_validation_error():
    with pytest.raises(ValidationError):
        SearchQuery(limit=2000)  # Limit exceeds the maximum allowed value


def test_search_query_added_range_order():
    with pytest.raises(ValidationError):
        SearchQuery(added_from=date(2026, 8, 10), added_to=date(2026, 8, 1))


def test_import_window_bounds_today():
    today = date(2026, 8, 28)
    assert import_window_bounds(ImportWindow.today, today=today) == (today, today)
    assert import_window_bounds("today", today=today) == (today, today)


def test_import_window_bounds_rolling():
    today = date(2026, 8, 28)
    assert import_window_bounds(ImportWindow.days_7, today=today) == (
        today - timedelta(days=6),
        today,
    )
    assert import_window_bounds(ImportWindow.days_30, today=today) == (
        today - timedelta(days=29),
        today,
    )
    assert import_window_bounds(ImportWindow.all, today=today) == (None, None)
    assert import_window_bounds("nope", today=today) == (None, None)


def test_added_date_sql_filter_empty_and_bounds():
    sql, params = added_date_sql_filter(None, None)
    assert sql == ""
    assert params == []

    sql, params = added_date_sql_filter(date(2026, 8, 1), date(2026, 8, 28))
    assert "date(d.added_date, 'localtime') >= date(?)" in sql
    assert "date(d.added_date, 'localtime') <= date(?)" in sql
    assert params == ["2026-08-01", "2026-08-28"]


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
