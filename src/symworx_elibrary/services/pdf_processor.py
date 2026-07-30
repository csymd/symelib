"""
src/symworx_elibrary/services/pdf_processor.py
"""

from pathlib import Path

import PyPDF2

from symworx_elibrary.models.document import DOI, PDFDocument
from symworx_elibrary.utils.doi_parser import (
    extract_doi_from_text,
    extract_pmid_from_text,
    normalize_doi,
)
from symworx_elibrary.utils.logging import LoggerConfig, get_shared_logger

# === Initialize Logger ===
logger = get_shared_logger(LoggerConfig(name="pdf_processor"))

# ========================================================= #
# PDF Processing Service                                    #
# ========================================================= #


class PDFProcessor:
    """Service for processing PDF files"""

    def __init__(self):
        logger.info("PDFProcessor initialized")

    def scan_directory(self, directory: Path) -> list[PDFDocument]:
        """Scan directory for PDF files"""
        logger.info("Starting directory scan", directory=str(directory))
        if not directory.exists():
            logger.error("Directory does not exist", directory=str(directory))
            raise ValueError(f"Directory does not exist: {directory}")

        pdf_files = list(directory.glob("**/*.pdf"))
        logger.info(
            "PDF files discovered",
            file_count=len(pdf_files),
            directory=str(directory),
        )

        documents = []

        for pdf_path in pdf_files:
            try:
                doc = PDFDocument(
                    file_path=pdf_path,
                    original_filename=pdf_path.name,
                    file_size=pdf_path.stat().st_size,
                )
                documents.append(doc)
                logger.debug("PDF document added", file_path=str(pdf_path))
            except Exception as e:
                logger.error("Error processing PDF file", file_path=str(pdf_path), error=str(e))
                print(f"Error processing {pdf_path}: {e}")

        return documents

    def extract_text(self, pdf_path: Path, max_pages: int | None = 3) -> str:
        """Extract text from a PDF.

        Args:
            pdf_path: Path to the PDF.
            max_pages: Number of pages to read from the start. None = all pages.
                       Default is small (3) for fast DOI/preview during ingestion.
                       Use a higher number (e.g. 40) or None when building embeddings/RAG.
        """
        text = ""
        try:
            with open(pdf_path, "rb") as file:
                reader = PyPDF2.PdfReader(file)
                total = len(reader.pages)
                if max_pages is None:
                    pages_to_read = total
                else:
                    pages_to_read = min(max_pages, total)

                for i in range(pages_to_read):
                    page = reader.pages[i]
                    page_text = page.extract_text() or ""
                    text += page_text + "\n\n"

        except Exception as e:
            print(f"Error extracting text from {pdf_path}: {e}")

        return text.strip()

    def extract_full_text(self, pdf_path: Path, max_pages: int | None = 40) -> str:
        """Convenience wrapper for higher-quality text suitable for embeddings / RAG.
        Reads up to ~40 pages by default (or all if None). Falls back to extract_text.
        """
        return self.extract_text(pdf_path, max_pages=max_pages)

    def find_doi(self, text: str) -> DOI | None:
        """Find and normalize a DOI in extracted text."""
        doi_string = extract_doi_from_text(text)
        if not doi_string:
            return None
        normalized = normalize_doi(doi_string)
        if not normalized:
            return None
        try:
            return DOI(value=normalized)
        except ValueError:
            return None

    def find_pmid(self, text: str) -> str | None:
        """Find a PMID mention in extracted text."""
        return extract_pmid_from_text(text)

    def process_document(self, document: PDFDocument) -> PDFDocument:
        """Process a single PDF document to extract text and find DOI"""
        text = self.extract_text(document.file_path)
        document.extracted_text_preview = text[:500]
        document.doi = self.find_doi(text)
        document.processed = True
        return document
