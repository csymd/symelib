"""
The elib <check-metadata> command: audit metadata quality in the local library.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from elib.models.metadata import (
    MetadataIssue,
    MetadataStatus,
    has_real_doi,
    has_real_pmid,
)
from elib.services.db_manager import DatabaseManager
from elib.services.pdf_processor import PDFProcessor
from elib.utils.doi_parser import (
    extract_doi_from_text,
    extract_pmid_from_filename,
    extract_pmid_from_text,
)

# ========================================================= #
# elib <check-metadata> command                             #
# ========================================================= #


def check_metadata(
    ctx: typer.Context,
    status: list[MetadataStatus] | None = typer.Option(
        None,
        "--status",
        help="Only list documents with this status (repeatable). Default: incomplete statuses.",
    ),
    issue: list[MetadataIssue] | None = typer.Option(
        None,
        "--issue",
        help="Filter by metadata_issue code (repeatable): no_text, no_identifier, …",
    ),
    limit: int = typer.Option(50, help="Max documents to list in detail."),
    as_json: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
    rebackfill: bool = typer.Option(
        False,
        "--rebackfill",
        help="Force re-classify all rows' metadata_status from current fields.",
    ),
    rediagnose: bool = typer.Option(
        False,
        "--rediagnose",
        help="Re-scan PDF text for existing rows and refresh text_extract_chars + issue "
        "when still fallback (does not call remote APIs).",
    ),
):
    """
    Audit document metadata quality and failure reasons.

    Issue codes (why enrichment failed):

      none            remote metadata ok
      no_text         PDF extract empty (scan / image-only)
      no_identifier   text ok but no DOI/PMID in PDF or filename
      pubmed_miss     had ID; PubMed miss
      crossref_miss   had DOI; Crossref also miss
      remote_error    network/API error
      parse_error     local processing exception
      unknown         legacy / not yet classified
    """
    config = ctx.obj["config"]
    db = DatabaseManager(config.database_path)

    if rebackfill:
        n = db.backfill_metadata_status(force=True)
        typer.echo(f"Re-classified metadata status for {n} document(s).")

    if rediagnose:
        n = _rediagnose_local(db)
        typer.echo(f"Re-diagnosed {n} document(s) from local PDF text (no remote calls).")

    counts = db.count_by_status()
    issues = db.count_by_issue()
    total = db.count_documents()
    fts = db.count_fts()

    list_statuses = status or [
        MetadataStatus.pending,
        MetadataStatus.partial,
        MetadataStatus.fallback,
    ]

    if issue:
        incomplete = db.list_by_issue(issue, limit=limit)
    else:
        incomplete = db.list_by_status(list_statuses, limit=limit)

    with_abstract = 0
    with_real_doi = 0
    with_real_pmid = 0
    for doc in db.list_documents():
        if doc.abstract and doc.abstract.strip():
            with_abstract += 1
        if has_real_doi(doc.doi):
            with_real_doi += 1
        if has_real_pmid(doc.pmid):
            with_real_pmid += 1

    if as_json:
        payload = {
            "total": total,
            "fts_count": fts,
            "by_status": counts,
            "by_issue": issues,
            "with_abstract": with_abstract,
            "with_real_doi": with_real_doi,
            "with_real_pmid": with_real_pmid,
            "documents": [
                {
                    "id": d.id,
                    "title": d.title,
                    "doi": d.doi or None,
                    "pmid": d.pmid,
                    "year": d.publication_year,
                    "metadata_status": d.metadata_status.value if d.metadata_status else None,
                    "metadata_source": d.metadata_source.value if d.metadata_source else None,
                    "metadata_issue": d.metadata_issue.value if d.metadata_issue else None,
                    "metadata_detail": d.metadata_detail,
                    "text_extract_chars": d.text_extract_chars,
                    "source_path": d.source_path,
                    "filename": d.filename,
                    "has_abstract": bool(d.abstract and d.abstract.strip()),
                }
                for d in incomplete
            ],
        }
        typer.echo(json.dumps(payload, indent=2))
        return

    typer.echo("=== Metadata quality audit ===\n")
    typer.echo(f"Total documents: {total}")
    typer.echo(f"FTS index rows:  {fts}")
    typer.echo(f"With abstract:   {with_abstract}")
    typer.echo(f"With real DOI:   {with_real_doi}")
    typer.echo(f"With real PMID:  {with_real_pmid}")

    typer.echo("\nBy status:")
    for key in (
        MetadataStatus.complete.value,
        MetadataStatus.partial.value,
        MetadataStatus.fallback.value,
        MetadataStatus.pending.value,
    ):
        typer.echo(f"  {key:12s} {counts.get(key, 0)}")

    typer.echo("\nBy issue (why incomplete / for re-run):")
    for key in (
        MetadataIssue.none.value,
        MetadataIssue.no_text.value,
        MetadataIssue.no_identifier.value,
        MetadataIssue.pubmed_miss.value,
        MetadataIssue.crossref_miss.value,
        MetadataIssue.remote_error.value,
        MetadataIssue.parse_error.value,
        MetadataIssue.unknown.value,
    ):
        n = issues.get(key, 0)
        if n or key in (
            MetadataIssue.no_text.value,
            MetadataIssue.no_identifier.value,
            MetadataIssue.unknown.value,
            MetadataIssue.none.value,
        ):
            typer.echo(f"  {key:16s} {n}")

    typer.echo(f"\nListed documents (up to {limit}):\n")
    if not incomplete:
        typer.echo("  (none)")
        return

    for d in incomplete:
        abs_flag = "abs" if d.abstract and d.abstract.strip() else "no-abs"
        chars = d.text_extract_chars if d.text_extract_chars is not None else "?"
        issue_v = d.metadata_issue.value if d.metadata_issue else "?"
        st = d.metadata_status.value if d.metadata_status else "?"
        typer.echo(f"  [{st:8s}/{issue_v:14s}] id={d.id}  chars={chars}  {d.title[:60]}")
        typer.echo(
            f"             doi={d.doi or '-'}  pmid={d.pmid or '-'}  {abs_flag}  file={d.filename[:40]}"
        )
        if d.metadata_detail:
            typer.echo(f"             note: {d.metadata_detail[:140]}")


def _rediagnose_local(db: DatabaseManager) -> int:
    """Refresh text_extract_chars + issue for fallback/unknown rows from local PDFs."""
    proc = PDFProcessor()
    updated = 0
    targets = db.list_by_status(
        [MetadataStatus.fallback, MetadataStatus.pending, MetadataStatus.partial],
        limit=None,
    )
    # list_by_status may not accept None limit - check
    if not targets:
        targets = [d for d in db.list_documents() if d.metadata_status != MetadataStatus.complete]

    for d in targets:
        if d.id is None:
            continue
        # Skip if already remote-complete
        if d.metadata_status == MetadataStatus.complete and d.metadata_issue == MetadataIssue.none:
            continue
        path = Path(d.file_path)
        if not path.exists():
            detail = f"File missing on disk: {path}"
            with db.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE documents SET
                        metadata_issue = ?,
                        metadata_detail = ?,
                        text_extract_chars = 0
                    WHERE id = ?
                    """,
                    (MetadataIssue.parse_error.value, detail, d.id),
                )
                conn.commit()
            updated += 1
            continue

        text = proc.extract_text(path, max_pages=5)
        chars = len(text or "")
        doi = extract_doi_from_text(text)
        pmid = (
            extract_pmid_from_text(text)
            or extract_pmid_from_filename(d.original_filename)
            or extract_pmid_from_filename(d.filename)
            or extract_pmid_from_filename(path.name)
            or extract_pmid_from_filename(d.title)  # URL-encoded cart titles
            or extract_pmid_from_filename(d.source_path)
        )

        if d.metadata_status in (MetadataStatus.complete, MetadataStatus.partial) and (
            has_real_doi(d.doi) or has_real_pmid(d.pmid)
        ):
            issue = MetadataIssue.none
            detail = None
        elif chars < 40:
            issue = MetadataIssue.no_text
            detail = f"PDF text extraction too short ({chars} chars); likely scanned/image-only."
        elif not doi and not pmid and not has_real_doi(d.doi) and not has_real_pmid(d.pmid):
            issue = MetadataIssue.no_identifier
            detail = f"Extracted {chars} chars but no DOI/PMID in PDF or filename."
        elif has_real_doi(d.doi) or has_real_pmid(d.pmid) or doi or pmid:
            # Had or now has identifier but status still fallback → remote miss previously
            issue = (
                MetadataIssue.pubmed_miss
                if (d.doi or d.pmid or doi or pmid)
                else MetadataIssue.no_identifier
            )
            detail = (
                f"Identifier available (doi={doi or d.doi or '—'}, pmid={pmid or d.pmid or '—'}); "
                f"re-run: elib enrich --id {d.id}  (text_chars={chars})"
            )
        else:
            issue = MetadataIssue.unknown
            detail = f"Unclassified; text_chars={chars}"

        # If we discovered a PMID in filename and row has none, stash in detail only
        # (enrich will pick it up when re-run if we write pmid)
        new_pmid = d.pmid
        if not has_real_pmid(d.pmid) and pmid:
            new_pmid = pmid
        new_doi = d.doi or ""
        if not has_real_doi(d.doi) and doi:
            new_doi = doi

        with db.get_connection() as conn:
            conn.execute(
                """
                UPDATE documents SET
                    metadata_issue = ?,
                    metadata_detail = ?,
                    text_extract_chars = ?,
                    doi = CASE WHEN (doi IS NULL OR doi = '') AND ? != '' THEN ? ELSE doi END,
                    pmid = CASE WHEN (pmid IS NULL OR pmid = '') AND ? IS NOT NULL THEN ? ELSE pmid END
                WHERE id = ?
                """,
                (
                    issue.value,
                    detail,
                    chars,
                    new_doi,
                    new_doi,
                    new_pmid,
                    new_pmid,
                    d.id,
                ),
            )
            conn.commit()
        updated += 1
    return updated
