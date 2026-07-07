"""
src/elib/services/pdf_processor.py
"""

from pathlib import Path
import re

import PyPDF2

from elib.models.document import DOI, PDFDocument
from elib.utils.logging import LoggerConfig, get_shared_logger

# === Initialize Logger ===
logger = get_shared_logger(LoggerConfig(name="pdf_processor"))

# ========================================================= #
# PDF Processing Service                                    #
# ========================================================= #


class PDFProcessor:
    """Service for processing PDF files"""

    DOI_PATTERNS = [
        r"10\.\d{4,}/[-._;()\/:A-Za-z0-9]+",
        r"doi:\s*10\.\d{4,}/[-._;()\/:A-Za-z0-9]+",
        r"DOI:\s*10\.\d{4,}/[-._;()\/:A-Za-z0-9]+",
    ]

    def __init__(self):
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.DOI_PATTERNS]
        logger.info("PDFProcessor initialized", pattern_count=len(self.compiled_patterns))

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
        """Find DOI in extracted text"""
        for pattern in self.compiled_patterns:
            match = pattern.search(text)
            if match:
                doi_string = match.group(0)
                # Clean up the DOI
                doi_string = doi_string.replace("doi:", "").replace("DOI:", "").strip()
                try:
                    return DOI(value=doi_string)
                except ValueError:
                    continue
        return None

    def process_document(self, document: PDFDocument) -> PDFDocument:
        """Process a single PDF document to extract text and find DOI"""
        text = self.extract_text(document.file_path)
        document.extracted_text_preview = text[:500]
        document.doi = self.find_doi(text)
        document.processed = True
        return document
