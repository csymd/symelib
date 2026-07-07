"""
The elib <stats> command to show library statistics.
"""

from __future__ import annotations

import typer

from elib.services.db_manager import DatabaseManager

# ================================================= #
# elib <stats> command                             #
# ================================================= #


def stats(
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    """Show library statistics"""
    config = ctx.obj["config"]
    db_manager = DatabaseManager(config.database_path)

    with db_manager.get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        synced = conn.execute("SELECT COUNT(*) FROM documents WHERE s3_synced = 1").fetchone()[0]
        years = conn.execute("""
            SELECT publication_year, COUNT(*) as count 
            FROM documents 
            WHERE publication_year IS NOT NULL
            GROUP BY publication_year 
            ORDER BY publication_year DESC
            LIMIT 10
        """).fetchall()

    typer.echo(f"Total documents: {total}")
    typer.echo(f"Synced to S3: {synced}")
    typer.echo("\nDocuments by year:")
    for row in years:
        typer.echo(f"  {row['publication_year']}: {row['count']}")
