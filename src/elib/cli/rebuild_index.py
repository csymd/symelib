"""
src/commands/rebuild_index.py

The elib <rebuild-index> command to rebuild the full-text search index.
"""
from __future__ import annotations

import typer

from elib.services.db_manager import DatabaseManager

# ========================================================= #
# elib <rebuild-index> command                              #
# ========================================================= #

def rebuild_index(ctx):
    """Rebuild the full-text search index."""
    config = ctx.obj['config']
    db_manager = DatabaseManager(config.database_path)
    
    typer.echo('Rebuilding FTS index...')
    count = db_manager.rebuild_fts_index()
    typer.echo(f'Rebuilt FTS index for {count} documents')
