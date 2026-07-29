"""
src/elib/services/file_manager.py
"""

from pathlib import Path
import shutil
from urllib.parse import unquote

from elib.models.document import DOI, PDFDocument, ProcessedDocument
from elib.services.crossref_client import CrossrefClient
from elib.services.db_manager import DatabaseManager
from elib.services.metadata_enricher import MetadataEnricher
from elib.services.ncbi_client import NCBIClient
from elib.services.pdf_processor import PDFProcessor
from elib.utils.doi_parser import (
    extract_identifiers_from_path,
    extract_pmid_from_filename,
    normalize_doi,
)
from elib.utils.logging import LoggerConfig, get_shared_logger

# === Initialize Logger ===
logger = get_shared_logger(LoggerConfig(name="file_manager"))

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
        crossref_client: CrossrefClient | None = None,
    ):
        self.pdf_processor = pdf_processor
        self.ncbi_client = ncbi_client
        self.db_manager = db_manager
        self.target_directory = target_directory
        self.target_directory.mkdir(parents=True, exist_ok=True)

        if crossref_client is None:
            crossref_client = CrossrefClient(mailto=ncbi_client.email)
        self.enricher = MetadataEnricher(
            ncbi_client=ncbi_client,
            crossref_client=crossref_client,
            db_manager=db_manager,
        )

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
                logger.error("process failed", path=str(doc.file_path), error=str(e))

        return processed, errors

    def process_single_document(self, document: PDFDocument) -> ProcessedDocument | None:
        """Process a single PDF document"""
        source_path = str(document.file_path.resolve())
        print(f"Processing: {document.file_path}")

        # Skip if this exact source file was already ingested
        existing_src = self.db_manager.get_by_source_path(source_path)
        if existing_src:
            print(
                f"  Already imported from source_path (id={existing_src.id}): {existing_src.filename}"
            )
            return None

        # Extract text and find DOI / PMID
        document = self.pdf_processor.process_document(document)
        full_preview = self.pdf_processor.extract_text(document.file_path, max_pages=5)
        text_chars = len(full_preview or "")
        document.extracted_text_preview = (full_preview or "")[:500]

        doi_str = document.doi.value if document.doi else None
        if not doi_str:
            found = self.pdf_processor.find_doi(full_preview)
            if found:
                doi_str = found.value
                document.doi = found

        pmid_hint = self.pdf_processor.find_pmid(full_preview)

        # Filename / path identifiers (e.g. "[15432688 - Journal....pdf")
        path_doi, path_pmid = extract_identifiers_from_path(document.file_path)
        if not doi_str and path_doi:
            doi_str = path_doi
            print(f"  DOI from filename: {doi_str}")
        if not pmid_hint and path_pmid:
            pmid_hint = path_pmid
            print(f"  PMID from filename: {pmid_hint}")
        # Also try original_filename field
        if not pmid_hint:
            pmid_hint = extract_pmid_from_filename(document.original_filename)

        if doi_str:
            print(f"  Found DOI: {doi_str}")
            existing = self.db_manager.get_by_doi(doi_str)
            if existing:
                print(f"  Already in database by DOI: {existing.filename}")
                return None
        elif pmid_hint:
            print(f"  Found PMID: {pmid_hint}")
        else:
            print(f"  No DOI/PMID (text_chars={text_chars})")

        # Readable title from URL-decoded original filename when possible
        raw_name = unquote(document.original_filename or document.file_path.name)
        fallback_title = Path(raw_name).stem.replace("_", " ")[:150] or "Untitled document"

        result = self.enricher.enrich(
            doi=doi_str,
            pmid=pmid_hint,
            fallback_title=fallback_title,
            fallback_abstract=document.extracted_text_preview if text_chars >= 40 else None,
            text_extract_chars=text_chars,
        )

        print(
            f"  Metadata: source={result.source.value} status={result.status.value} "
            f"issue={result.issue.value}"
        )
        if result.detail:
            print(f"  Detail: {result.detail[:160]}")
        print(f"  Title: {result.reference.title[:70]}...")
        if result.reference.pmid:
            print(f"  PMID: {result.reference.pmid}")
        if result.reference.doi:
            print(f"  DOI: {result.reference.doi}")

        # Dedup by DOI after enrichment
        final_doi = normalize_doi(result.reference.doi) if result.reference.doi else None
        if final_doi:
            existing = self.db_manager.get_by_doi(final_doi)
            if existing:
                print(f"  Already in database after enrich: {existing.filename}")
                return None

        return self._finish_processing(
            document,
            result,
            source_path=source_path,
            original_filename=document.original_filename,
        )

    def _finish_processing(
        self,
        document: PDFDocument,
        enrichment,
        *,
        source_path: str | None,
        original_filename: str | None,
    ) -> ProcessedDocument:
        """Copy file, insert DB row, return ProcessedDocument."""
        reference = enrichment.reference
        try:
            new_filename = reference.generate_filename()
        except Exception:
            safe = (
                "".join(c for c in reference.title if c.isalnum() or c in " _-")[:40]
                .strip()
                .replace(" ", "_")
            )
            new_filename = f"{safe or 'doc'}.pdf"

        # Avoid ugly Unknown_NODATE_URLENCODED for local fallbacks
        if enrichment.source.value == "local" and original_filename:
            stem = Path(unquote(original_filename)).stem
            clean = "".join(c if c.isalnum() or c in " _-" else "_" for c in stem)[:60]
            clean = clean.strip("_ ") or "doc"
            new_filename = f"{clean}.pdf"

        new_path = self.target_directory / new_filename
        counter = 1
        while new_path.exists():
            stem = new_path.stem
            new_path = self.target_directory / f"{stem}_{counter}.pdf"
            counter += 1

        shutil.copy2(document.file_path, new_path)
        print(f"  Copied to: {new_path}")

        doc_id = self.db_manager.add_document(
            reference=reference,
            file_path=new_path,
            filename=new_path.name,
            file_size=document.file_size,
            metadata_status=enrichment.status,
            metadata_source=enrichment.source,
            metadata_checked_at=enrichment.checked_at,
            metadata_issue=enrichment.issue,
            metadata_detail=enrichment.detail,
            text_extract_chars=enrichment.text_extract_chars,
            source_path=source_path,
            original_filename=original_filename,
        )
        print(f"  Added to database with ID: {doc_id}")

        final_doi = document.doi
        if not final_doi and reference.doi:
            try:
                norm = normalize_doi(reference.doi)
                if norm:
                    final_doi = DOI(value=norm)
            except Exception:
                final_doi = None

        return ProcessedDocument(
            file_path=new_path,
            original_filename=document.original_filename,
            file_size=document.file_size,
            doi=final_doi,
            new_filename=new_path.name,
            pmid=reference.pmid or None,
            metadata_stored=True,
        )
