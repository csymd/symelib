"""
Orchestrate PubMed → Crossref → local fallback metadata enrichment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from elib.models.metadata import (
    MetadataIssue,
    MetadataSource,
    MetadataStatus,
    classify_metadata_status,
    has_real_doi,
    has_real_pmid,
)
from elib.models.reference import Journal, Reference
from elib.services.crossref_client import CrossrefClient
from elib.services.db_manager import DatabaseManager
from elib.services.ncbi_client import NCBIClient
from elib.utils.doi_parser import normalize_doi
from elib.utils.logging import LoggerConfig, get_shared_logger

logger = get_shared_logger(LoggerConfig(name="metadata_enricher"))


@dataclass
class EnrichmentResult:
    """Outcome of a single enrichment attempt."""

    reference: Reference
    status: MetadataStatus
    source: MetadataSource
    checked_at: datetime
    issue: MetadataIssue = MetadataIssue.none
    detail: str | None = None
    text_extract_chars: int | None = None
    # trail of what we tried (for metadata_detail)
    attempts: list[str] = field(default_factory=list)


class MetadataEnricher:
    """Resolve bibliographic metadata for a document via remote sources."""

    def __init__(
        self,
        ncbi_client: NCBIClient,
        crossref_client: CrossrefClient | None = None,
        db_manager: DatabaseManager | None = None,
    ):
        self.ncbi = ncbi_client
        self.crossref = crossref_client
        self.db = db_manager

    def enrich(
        self,
        *,
        doi: str | None = None,
        pmid: str | None = None,
        fallback_title: str | None = None,
        fallback_abstract: str | None = None,
        text_extract_chars: int | None = None,
    ) -> EnrichmentResult:
        """
        Try PubMed (by PMID or DOI), then Crossref (by DOI), else local fallback.

        Does not write to the database — caller decides insert vs update.
        Always populates ``issue`` / ``detail`` for diagnostics.
        """
        checked_at = datetime.now()
        attempts: list[str] = []
        doi_n = normalize_doi(doi) if doi else None
        pmid_n = (
            pmid.strip()
            if pmid and pmid.strip() and not pmid.upper().startswith("LOCAL-")
            else None
        )

        text_chars = (
            text_extract_chars
            if text_extract_chars is not None
            else (len(fallback_abstract) if fallback_abstract else 0)
        )

        # Fast path: nothing extractable and no identifiers
        if not doi_n and not pmid_n:
            if text_chars < 40:
                issue = MetadataIssue.no_text
                detail = (
                    f"PDF text extraction too short ({text_chars} chars); "
                    "likely scanned/image-only. OCR not yet enabled."
                )
            else:
                issue = MetadataIssue.no_identifier
                detail = (
                    f"Extracted {text_chars} chars of text but found no DOI/PMID "
                    "(in PDF or filename)."
                )
            attempts.append(detail)
            return self._fallback(
                fallback_title=fallback_title,
                fallback_abstract=fallback_abstract,
                doi_n=None,
                checked_at=checked_at,
                issue=issue,
                detail=detail,
                text_extract_chars=text_chars,
                attempts=attempts,
            )

        # 1) PubMed by PMID
        if pmid_n:
            attempts.append(f"pubmed:fetch_pmid={pmid_n}")
            try:
                ref = self.ncbi.fetch_reference(pmid_n)
            except Exception as e:
                attempts.append(f"pubmed:error={e}")
                logger.error("PubMed fetch failed", pmid=pmid_n, error=str(e))
                ref = None
                if not doi_n:
                    return self._fallback(
                        fallback_title=fallback_title,
                        fallback_abstract=fallback_abstract,
                        doi_n=doi_n,
                        checked_at=checked_at,
                        issue=MetadataIssue.remote_error,
                        detail=f"PubMed error for PMID {pmid_n}: {e}",
                        text_extract_chars=text_chars,
                        attempts=attempts,
                    )
            if ref and (ref.title and ref.title != "No title"):
                return self._result(
                    ref,
                    MetadataSource.pubmed,
                    checked_at,
                    text_extract_chars=text_chars,
                    attempts=attempts + ["pubmed:ok"],
                )
            attempts.append("pubmed:pmid_miss")

        # 2) PubMed by DOI
        if doi_n:
            attempts.append(f"pubmed:search_doi={doi_n}")
            try:
                found_pmid = self.ncbi.search_by_doi(doi_n)
            except Exception as e:
                attempts.append(f"pubmed:search_error={e}")
                found_pmid = None
            if found_pmid:
                attempts.append(f"pubmed:fetch_pmid={found_pmid}")
                try:
                    ref = self.ncbi.fetch_reference(found_pmid)
                except Exception as e:
                    attempts.append(f"pubmed:fetch_error={e}")
                    ref = None
                if ref:
                    if not ref.doi:
                        ref = ref.model_copy(update={"doi": doi_n})
                    return self._result(
                        ref,
                        MetadataSource.pubmed,
                        checked_at,
                        text_extract_chars=text_chars,
                        attempts=attempts + ["pubmed:ok"],
                    )
            attempts.append("pubmed:doi_miss")

        # 3) Crossref by DOI
        if doi_n and self.crossref is not None:
            attempts.append(f"crossref:fetch={doi_n}")
            try:
                ref = self.crossref.fetch_by_doi(doi_n)
            except Exception as e:
                attempts.append(f"crossref:error={e}")
                ref = None
            if ref and ref.title and ref.title != "No title":
                return self._result(
                    ref,
                    MetadataSource.crossref,
                    checked_at,
                    text_extract_chars=text_chars,
                    attempts=attempts + ["crossref:ok"],
                )
            attempts.append("crossref:miss")
            issue = MetadataIssue.crossref_miss
            detail = f"DOI {doi_n} not found in PubMed or Crossref (text_chars={text_chars})."
        elif doi_n or pmid_n:
            issue = MetadataIssue.pubmed_miss
            detail = (
                f"Identifier present (doi={doi_n or '—'}, pmid={pmid_n or '—'}) "
                f"but PubMed returned no usable record; Crossref not tried "
                f"(text_chars={text_chars})."
            )
        else:
            issue = MetadataIssue.no_identifier
            detail = "No identifiers after remote attempts."

        return self._fallback(
            fallback_title=fallback_title,
            fallback_abstract=fallback_abstract,
            doi_n=doi_n,
            checked_at=checked_at,
            issue=issue,
            detail=detail,
            text_extract_chars=text_chars,
            attempts=attempts,
        )

    def enrich_document_row(self, doc_id: int, *, dry_run: bool = False) -> EnrichmentResult | None:
        """Re-enrich an existing DB row by id. Updates DB unless dry_run.

        Re-reads the PDF when present to refresh text_chars and pick up
        DOI/PMID that may have been missed (including filename PMIDs).
        """
        if self.db is None:
            raise RuntimeError("DatabaseManager required for enrich_document_row")

        meta = self.db.get_by_id(doc_id)
        if meta is None:
            return None

        doi = meta.doi if has_real_doi(meta.doi) else None
        pmid = meta.pmid if has_real_pmid(meta.pmid) else None
        text_chars = meta.text_extract_chars
        fallback_abstract = meta.abstract

        # Local re-scan of PDF + filename for better identifiers
        try:
            from pathlib import Path

            from elib.services.pdf_processor import PDFProcessor
            from elib.utils.doi_parser import (
                extract_doi_from_text,
                extract_pmid_from_filename,
                extract_pmid_from_text,
            )

            path = Path(meta.file_path)
            if path.exists():
                text = PDFProcessor().extract_text(path, max_pages=5)
                text_chars = len(text or "")
                doi = doi or extract_doi_from_text(text)
                pmid = (
                    pmid
                    or extract_pmid_from_text(text)
                    or extract_pmid_from_filename(meta.original_filename or meta.filename)
                    or extract_pmid_from_filename(path.name)
                )
                if text_chars >= 40 and not fallback_abstract:
                    fallback_abstract = text[:500]
        except Exception as e:
            logger.warning("local re-scan failed", doc_id=doc_id, error=str(e))

        result = self.enrich(
            doi=doi,
            pmid=pmid,
            fallback_title=meta.title,
            fallback_abstract=fallback_abstract,
            text_extract_chars=text_chars,
        )

        if dry_run:
            return result

        self.db.update_document_metadata(
            doc_id,
            result.reference,
            metadata_status=result.status,
            metadata_source=result.source,
            metadata_checked_at=result.checked_at,
            metadata_issue=result.issue,
            metadata_detail=result.detail,
            text_extract_chars=result.text_extract_chars,
        )
        return result

    def _fallback(
        self,
        *,
        fallback_title: str | None,
        fallback_abstract: str | None,
        doi_n: str | None,
        checked_at: datetime,
        issue: MetadataIssue,
        detail: str,
        text_extract_chars: int | None,
        attempts: list[str],
    ) -> EnrichmentResult:
        title = (fallback_title or "Untitled document").strip() or "Untitled document"
        ref = Reference(
            pmid="",
            doi=doi_n or "",
            title=title[:300],
            authors=[],
            journal=Journal(title="Local / Non-PubMed source"),
            publication_date=None,
            abstract=fallback_abstract,
            keywords=[],
            mesh_terms=[],
        )
        full_detail = detail
        if attempts:
            full_detail = f"{detail} | trail: {'; '.join(attempts[-8:])}"
        return EnrichmentResult(
            reference=ref,
            status=MetadataStatus.fallback,
            source=MetadataSource.local,
            checked_at=checked_at,
            issue=issue,
            detail=full_detail[:2000],
            text_extract_chars=text_extract_chars,
            attempts=attempts,
        )

    @staticmethod
    def _result(
        ref: Reference,
        source: MetadataSource,
        checked_at: datetime,
        *,
        text_extract_chars: int | None = None,
        attempts: list[str] | None = None,
    ) -> EnrichmentResult:
        status = classify_metadata_status(
            doi=ref.doi,
            pmid=ref.pmid or None,
            title=ref.title,
            authors_json='[{"last_name":"x"}]' if ref.authors else "[]",
            abstract=ref.abstract,
        )
        if status == MetadataStatus.fallback and (ref.doi or ref.pmid):
            status = MetadataStatus.partial
        return EnrichmentResult(
            reference=ref,
            status=status,
            source=source,
            checked_at=checked_at,
            issue=MetadataIssue.none,
            detail=None,
            text_extract_chars=text_extract_chars,
            attempts=list(attempts or []),
        )
