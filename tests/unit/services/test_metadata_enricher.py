"""
tests/unit/services/test_metadata_enricher.py
"""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from symworx_elibrary.models.metadata import MetadataSource, MetadataStatus
from symworx_elibrary.models.reference import Author, Journal, Reference
from symworx_elibrary.services.db_manager import DatabaseManager
from symworx_elibrary.services.metadata_enricher import MetadataEnricher


def _ref(**kw) -> Reference:
    base = dict(
        pmid="123",
        doi="10.1234/abc",
        title="Remote Title",
        authors=[Author(last_name="A", first_name="B", initials="B")],
        journal=Journal(title="J"),
        publication_date=date(2020, 1, 1),
        abstract="Abs",
        keywords=[],
        mesh_terms=[],
    )
    base.update(kw)
    return Reference(**base)


def test_enrich_prefers_pubmed_by_doi():
    ncbi = MagicMock()
    ncbi.search_by_doi.return_value = "123"
    ncbi.fetch_reference.return_value = _ref()
    crossref = MagicMock()

    enricher = MetadataEnricher(ncbi_client=ncbi, crossref_client=crossref)
    result = enricher.enrich(doi="10.1234/abc")

    assert result.source == MetadataSource.pubmed
    assert result.status == MetadataStatus.complete
    assert result.reference.title == "Remote Title"
    crossref.fetch_by_doi.assert_not_called()


def test_enrich_falls_back_to_crossref():
    ncbi = MagicMock()
    ncbi.search_by_doi.return_value = None
    ncbi.fetch_reference.return_value = None
    crossref = MagicMock()
    crossref.fetch_by_doi.return_value = _ref(pmid="", abstract=None)

    enricher = MetadataEnricher(ncbi_client=ncbi, crossref_client=crossref)
    result = enricher.enrich(doi="10.1234/abc")

    assert result.source == MetadataSource.crossref
    assert result.status == MetadataStatus.partial  # no abstract
    crossref.fetch_by_doi.assert_called_once()


def test_enrich_local_fallback():
    from symworx_elibrary.models.metadata import MetadataIssue

    ncbi = MagicMock()
    ncbi.search_by_doi.return_value = None
    crossref = MagicMock()
    crossref.fetch_by_doi.return_value = None

    enricher = MetadataEnricher(ncbi_client=ncbi, crossref_client=crossref)
    result = enricher.enrich(
        fallback_title="My Local Paper",
        fallback_abstract="preview text that is long enough to not count as no_text xxx",
        text_extract_chars=200,
    )

    assert result.source == MetadataSource.local
    assert result.status == MetadataStatus.fallback
    assert result.issue == MetadataIssue.no_identifier
    assert result.reference.title == "My Local Paper"
    assert result.reference.doi == ""
    assert result.reference.pmid == ""


def test_enrich_no_text_issue():
    from symworx_elibrary.models.metadata import MetadataIssue

    ncbi = MagicMock()
    crossref = MagicMock()
    enricher = MetadataEnricher(ncbi_client=ncbi, crossref_client=crossref)
    result = enricher.enrich(fallback_title="scan.pdf", text_extract_chars=0)
    assert result.issue == MetadataIssue.no_text
    ncbi.search_by_doi.assert_not_called()


def test_enrich_document_row_updates_db(tmp_path: Path):
    db = DatabaseManager(tmp_path / "t.db")
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    doc_id = db.add_document(
        _ref(doi="10.9999/x", pmid="LOCAL-1", title="Old", authors=[], abstract=None),
        file_path=pdf,
        filename=pdf.name,
        file_size=4,
        metadata_status=MetadataStatus.fallback,
        metadata_source=MetadataSource.local,
    )

    ncbi = MagicMock()
    ncbi.search_by_doi.return_value = "999"
    # After synthetic strip, no real doi — enrich will try with doi=None
    # So seed a real DOI on the row first
    db.update_document_metadata(
        doc_id,
        _ref(doi="10.1234/real", pmid="", title="Stub", authors=[], abstract=None),
        metadata_status=MetadataStatus.partial,
        metadata_source=MetadataSource.local,
    )

    ncbi.search_by_doi.return_value = "999"
    ncbi.fetch_reference.return_value = _ref(doi="10.1234/real", pmid="999")

    enricher = MetadataEnricher(ncbi_client=ncbi, crossref_client=None, db_manager=db)
    result = enricher.enrich_document_row(doc_id)
    assert result is not None
    assert result.source == MetadataSource.pubmed

    updated = db.get_by_id(doc_id)
    assert updated is not None
    assert updated.metadata_status == MetadataStatus.complete
    assert updated.pmid == "999"
    assert updated.title == "Remote Title"
