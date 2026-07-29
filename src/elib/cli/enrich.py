"""
The elib <enrich> command: re-fetch metadata for incomplete library records.
"""

from __future__ import annotations

import time

import typer

from elib.models.metadata import MetadataIssue, MetadataStatus
from elib.services.crossref_client import CrossrefClient
from elib.services.db_manager import DatabaseManager
from elib.services.metadata_enricher import MetadataEnricher
from elib.services.ncbi_client import NCBIClient
from elib.utils.rate_limiter import configure_process_delay

# ========================================================= #
# elib <enrich> command                                     #
# ========================================================= #


def enrich(
    ctx: typer.Context,
    doi: str | None = typer.Option(None, help="Enrich a single document by DOI."),
    doc_id: int | None = typer.Option(None, "--id", help="Enrich a single document by id."),
    status: list[MetadataStatus] | None = typer.Option(
        None,
        "--status",
        help="Only enrich documents with this status (repeatable). "
        "Default: pending, partial, fallback.",
    ),
    issue: list[MetadataIssue] | None = typer.Option(
        None,
        "--issue",
        help="Only enrich rows with this metadata_issue (e.g. no_identifier, pubmed_miss).",
    ),
    limit: int = typer.Option(100, help="Max documents to enrich in bulk mode."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change; no DB writes."),
    sleep: float = typer.Option(
        0.5,
        help="Min seconds between remote HTTP calls (raise if you hit 429s).",
    ),
):
    """
    Re-fetch metadata from PubMed (then Crossref) for library documents.

    Examples:

        elib enrich
        elib enrich --status fallback --limit 20
        elib enrich --issue no_identifier
        elib enrich --issue pubmed_miss --limit 50
        elib enrich --doi 10.1038/nature12373
        elib enrich --id 42 --dry-run
    """
    config = ctx.obj["config"]
    configure_process_delay(sleep)
    db = DatabaseManager(config.database_path)
    ncbi = NCBIClient(email=config.ncbi_email, api_key=config.ncbi_api_key)
    crossref = CrossrefClient(mailto=config.ncbi_email)
    enricher = MetadataEnricher(ncbi_client=ncbi, crossref_client=crossref, db_manager=db)

    targets: list[int] = []

    if doc_id is not None:
        targets = [doc_id]
    elif doi:
        meta = db.get_by_doi(doi)
        if not meta or meta.id is None:
            typer.echo(f"No document found with DOI: {doi}")
            raise typer.Exit(code=1)
        targets = [meta.id]
    elif issue:
        docs = db.list_by_issue(issue, limit=limit)
        targets = [d.id for d in docs if d.id is not None]
    else:
        statuses = status or [
            MetadataStatus.pending,
            MetadataStatus.partial,
            MetadataStatus.fallback,
        ]
        docs = db.list_by_status(statuses, limit=limit)
        targets = [d.id for d in docs if d.id is not None]

    if not targets:
        typer.echo("No documents to enrich.")
        return

    typer.echo(f"Enriching {len(targets)} document(s)" + (" [dry-run]" if dry_run else "") + "…")

    ok = 0
    failed = 0
    for i, tid in enumerate(targets, 1):
        before = db.get_by_id(tid)
        if before is None:
            typer.echo(f"  [{i}/{len(targets)}] id={tid} — not found, skip")
            failed += 1
            continue

        try:
            result = enricher.enrich_document_row(tid, dry_run=dry_run)
        except Exception as e:
            typer.echo(f"  [{i}/{len(targets)}] id={tid} — error: {e}")
            failed += 1
            continue

        if result is None:
            failed += 1
            continue

        title_snip = result.reference.title[:60]
        before_issue = before.metadata_issue.value if before.metadata_issue else "?"
        typer.echo(
            f"  [{i}/{len(targets)}] id={tid}  "
            f"{before.metadata_status.value}/{before_issue} → "
            f"{result.status.value}/{result.issue.value}  "
            f"via {result.source.value}  | {title_snip}"
        )
        ok += 1

        if i < len(targets) and sleep > 0:
            time.sleep(sleep)

    typer.echo(
        f"\nDone. updated/processed={ok} failed={failed}" + (" (dry-run)" if dry_run else "")
    )
