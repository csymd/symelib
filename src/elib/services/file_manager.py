"""
src/elib/services/file_manager.py
"""

from pathlib import Path
import shutil

from elib.models.document import PDFDocument, ProcessedDocument

# from elib.models.reference import Reference
from elib.services.db_manager import DatabaseManager
from elib.services.ncbi_client import NCBIClient
from elib.services.pdf_processor import PDFProcessor

from elib.models.reference import Author, Journal, Reference
from elib.utils.logging import LoggerConfig, get_shared_logger

# === Initialize Logger ===
logger = get_shared_logger(LoggerConfig(name="db_manager"))

# ========================================================= #
# File Manager Service                                      #
# ========================================================= #


class FileManager:
    """Service for managing PDF files and metadata"""

    def __init__(
        self,
        pdf_processor: PDFProcessor,
        ncbi_client: NCBIClient,
        db_manager: DatabaseManager,
        target_directory: Path,
    ):
        self.pdf_processor = pdf_processor
        self.ncbi_client = ncbi_client
        self.db_manager = db_manager
        self.target_directory = target_directory
        self.target_directory.mkdir(parents=True, exist_ok=True)

    def process_directory(self, source_dir: Path) -> tuple[list[ProcessedDocument], list[str]]:
        """Process all PDF documents in the source directory"""
        documents = self.pdf_processor.scan_directory(source_dir)
        processed = []
        errors = []

        for doc in documents:
            try:
                result = self.process_single_document(doc)
                if result:
                    processed.append(result)
            except Exception as e:
                errors.append(f"{doc.file_path}: {e!s}")

        return processed, errors

    def process_single_document(self, document: PDFDocument) -> ProcessedDocument | None:
        """Process a single PDF document"""
        print(f"Processing: {document.file_path}")

        # Extract text and find DOI
        document = self.pdf_processor.process_document(document)

        doi_str = document.doi.value if document.doi else None

        if doi_str:
            print(f"  Found DOI: {doi_str}")

            # Check if already in database
            existing = self.db_manager.get_by_doi(doi_str)
            if existing:
                print(f"  Already in database: {existing.filename}")
                return None

            # Search NCBI
            pmid = self.ncbi_client.search_by_doi(doi_str)
            if pmid:
                print(f"  Found PMID: {pmid}")
                reference = self.ncbi_client.fetch_reference(pmid)
                if reference:
                    print(f"  Title: {reference.title[:60]}...")
                    return self._finish_processing(document, reference, doi_str, pmid)

            print(f"  No PMID or reference for DOI (falling back to local metadata)")

        # Fallback for files without DOI/PMID (books, preprints, local files, user's general library)
        print("  Using local fallback metadata (no DOI/PMID from NCBI)")
        safe_title = document.file_path.stem.replace("_", " ").replace(".pdf", "").replace(".PDF", "")[:150]
        reference = Reference(
            pmid=f"LOCAL-{abs(hash(str(document.file_path))) % 10000000}",
            doi=doi_str or f"10.9999/elib-local-{abs(hash(str(document.file_path))) % 1000000}",
            title=safe_title or "Untitled document",
            authors=[],
            journal=Journal(title="Local / Non-PubMed source"),
            publication_date=None,
            abstract=document.extracted_text_preview,
            keywords=[],
            mesh_terms=[],
        )
        pmid = reference.pmid
        print(f"  Title (fallback): {reference.title[:60]}...")

        return self._finish_processing(document, reference, doi_str, pmid)

    def _finish_processing(
        self,
        document: PDFDocument,
        reference: Reference,
        doi_str: str | None,
        pmid: str,
    ) -> ProcessedDocument:
        """Common finish logic for both DOI path and fallback."""
        # Generate new filename (Reference has generate_filename)
        try:
            new_filename = reference.generate_filename()
        except Exception:
            # Fallback filename if generate_filename chokes on minimal data
            safe = "".join(c for c in reference.title if c.isalnum() or c in " _-")[:40].strip().replace(" ", "_")
            new_filename = f"{safe or 'doc'}.pdf"

        new_path = self.target_directory / new_filename

        # Handle filename conflicts
        counter = 1
        while new_path.exists():
            stem = new_path.stem
            new_path = self.target_directory / f"{stem}_{counter}.pdf"
            counter += 1

        # Copy/move file
        shutil.copy2(document.file_path, new_path)
        print(f"  Copied to: {new_path}")

        # Add to database
        doc_id = self.db_manager.add_document(
            reference=reference,
            file_path=new_path,
            filename=new_path.name,
            file_size=document.file_size,
        )
        print(f"  Added to database with ID: {doc_id}")

        # For ProcessedDocument, satisfy the (currently strict) doi field
        from elib.models.document import DOI
        final_doi = document.doi
        if not final_doi and doi_str:
            try:
                final_doi = DOI(value=doi_str)
            except Exception:
                final_doi = DOI(value="10.9999/elib-local-fallback")
        if not final_doi:
            final_doi = DOI(value="10.9999/elib-local-fallback")

        return ProcessedDocument(
            file_path=new_path,
            original_filename=document.original_filename,
            file_size=document.file_size,
            doi=final_doi,
            new_filename=new_path.name,
            pmid=pmid,
            metadata_stored=True,
        )
