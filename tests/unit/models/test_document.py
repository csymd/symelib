"""
tests/unit/models/test_document.py
"""

from datetime import datetime
from pathlib import Path

from pydantic import ValidationError
import pytest

from symworx_elibrary.models.document import (
    DOI,
    PDFDocument,
    ProcessedDocument,
)


# Test for DOI model
def test_doi_validation():
    valid_doi = "10.1234/abcd.efgh"
    doi = DOI(value=valid_doi)
    assert str(doi) == valid_doi

    invalid_doi = "invalid_doi"
    with pytest.raises(ValidationError):
        DOI(value=invalid_doi)


def test_doi_strip_whitespace():
    doi_with_whitespace = " 10.1234/abcd.efgh "
    doi = DOI(value=doi_with_whitespace)
    assert str(doi) == "10.1234/abcd.efgh"


# Test for PDFDocument model
def test_pdf_document_creation():
    pdf_path = Path("/path/to/document.pdf")
    pdf_doc = PDFDocument(
        file_path=pdf_path,
        original_filename="document.pdf",
        file_size=1024,
        extracted_text_preview="This is a preview of the document.",
    )
    assert pdf_doc.file_path == pdf_path
    assert pdf_doc.original_filename == "document.pdf"
    assert pdf_doc.file_size == 1024
    assert pdf_doc.extracted_text_preview == "This is a preview of the document."
    assert isinstance(pdf_doc.scan_date, datetime)
    assert pdf_doc.processed is False


def test_pdf_document_invalid_file_extension():
    invalid_path = Path("/path/to/document.txt")
    with pytest.raises(ValidationError):
        PDFDocument(
            file_path=invalid_path,
            original_filename="document.txt",
            file_size=1024,
        )


def test_pdf_document_extracted_text_length():
    long_text = "a" * 600  # 600 characters, exceeding the max_length of 500
    with pytest.raises(ValidationError):
        PDFDocument(
            file_path=Path("/path/to/document.pdf"),
            original_filename="document.pdf",
            file_size=1024,
            extracted_text_preview=long_text,
        )


# Test for ProcessedDocument model
def test_processed_document_creation():
    pdf_path = Path("/path/to/document.pdf")
    doi = DOI(value="10.1234/abcd.efgh")
    processed_doc = ProcessedDocument(
        file_path=pdf_path,
        original_filename="document.pdf",
        file_size=2048,
        doi=doi,
        new_filename="processed_document.pdf",
        pmid="12345678",
        metadata_stored=True,
    )
    assert processed_doc.file_path == pdf_path
    assert processed_doc.doi == doi
    assert processed_doc.new_filename == "processed_document.pdf"
    assert processed_doc.pmid == "12345678"
    assert processed_doc.processed is True
    assert processed_doc.metadata_stored is True


def test_processed_document_optional_doi():
    """Local-only papers may have no real DOI after honest fallback."""
    pdf_path = Path("/path/to/document.pdf")
    processed_doc = ProcessedDocument(
        file_path=pdf_path,
        original_filename="document.pdf",
        file_size=2048,
        new_filename="processed_document.pdf",
    )
    assert processed_doc.doi is None
    assert processed_doc.processed is True
