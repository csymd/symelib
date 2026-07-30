"""
The elib <rebuild-index> command to rebuild the full-text search index (SQLite FTS)
and optionally populate a PGVector index with real PDF text chunks for the agents/RAG path.
"""

from __future__ import annotations

import typer

from symworx_elibrary.services.db_manager import DatabaseManager

# ========================================================= #
# elib <rebuild-index> command                              #
# ========================================================= #


def rebuild_index(
    ctx: typer.Context,
    embeddings: bool = typer.Option(
        False,
        "--embeddings",
        help="Extract text from stored PDFs, chunk, and embed into Postgres+pgvector (needs [agents] + 'make db-up')",
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        "--clear-embeddings",
        help="Before populating, clear ALL existing vector embeddings (use with --embeddings)",
    ),
):
    """Rebuild the full-text search index (and optionally populate vector embeddings for RAG)."""
    config = ctx.obj["config"]
    db_manager = DatabaseManager(config.database_path)

    if embeddings:
        typer.echo("Embeddings population requested (--embeddings).")
        if reset:
            typer.echo(
                "  --reset / --clear-embeddings was passed: will remove ALL previous chunks first."
            )
        else:
            typer.echo(
                "  Will perform smart update (remove old chunks for these papers, then insert fresh ones)."
            )
        typer.echo(
            "Using stored PDFs for full(ish) text + chunking -> PGVector (needs [agents] + 'make db-up')."
        )

        try:
            from symworx_elibrary.agents.index import populate_embeddings

            num_sources = populate_embeddings(db_manager, reset=reset)
            typer.echo(f"Embeddings population finished for {num_sources} source papers.")
        except ImportError as e:
            typer.echo(f"[yellow]Could not load agents embedding code: {e}[/yellow]")
            typer.echo("Make sure you ran: uv sync --extra agents  (or --all-extras)")
            typer.echo("Then ensure the DB is up: make db-up")
        except Exception as e:
            typer.echo(f"[red]Embeddings population failed: {e}[/red]")
            typer.echo(
                "Common causes: Postgres not running (make db-up), missing PDFs on disk, or connection issues."
            )
            # Continue to FTS rebuild so the user still gets something useful

    typer.echo("Rebuilding FTS index (SQLite)...")
    count = db_manager.rebuild_fts_index()
    typer.echo(f"Rebuilt FTS index for {count} documents")
