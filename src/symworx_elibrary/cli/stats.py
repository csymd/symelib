"""
The elib <stats> command to show library statistics.
"""

from __future__ import annotations

import typer

from symworx_elibrary.models.metadata import MetadataStatus
from symworx_elibrary.services.db_manager import DatabaseManager

# ================================================= #
# elib <stats> command                             #
# ================================================= #


def stats(
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    """Show library statistics"""
    config = ctx.obj["config"]
    db_manager = DatabaseManager(config.database_path)

    total = db_manager.count_documents()
    fts = db_manager.count_fts()
    status_counts = db_manager.count_by_status()
    issue_counts = db_manager.count_by_issue()

    with db_manager.get_connection() as conn:
        synced = conn.execute("SELECT COUNT(*) FROM documents WHERE s3_synced = 1").fetchone()[0]
        with_abstract = conn.execute(
            """
            SELECT COUNT(*) FROM documents
            WHERE abstract IS NOT NULL AND TRIM(abstract) != ''
            """
        ).fetchone()[0]
        years = conn.execute("""
            SELECT publication_year, COUNT(*) as count
            FROM documents
            WHERE publication_year IS NOT NULL
            GROUP BY publication_year
            ORDER BY publication_year DESC
            LIMIT 10
        """).fetchall()

    typer.echo(f"Total documents: {total}")
    typer.echo(f"FTS index rows:  {fts}")
    typer.echo(f"With abstract:   {with_abstract}")
    typer.echo(f"Synced to S3:    {synced}")
    typer.echo(f"Database:        {config.database_path}")

    typer.echo("\nMetadata status:")
    for key in (
        MetadataStatus.complete.value,
        MetadataStatus.partial.value,
        MetadataStatus.fallback.value,
        MetadataStatus.pending.value,
    ):
        typer.echo(f"  {key:10s} {status_counts.get(key, 0)}")

    typer.echo("\nMetadata issues (re-run queues):")
    for key, n in sorted(issue_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        typer.echo(f"  {key:16s} {n}")

    typer.echo("\nDocuments by year:")
    if not years:
        typer.echo("  (none)")
    for row in years:
        typer.echo(f"  {row['publication_year']}: {row['count']}")
