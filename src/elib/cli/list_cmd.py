"""
The elib <list> command group: named paper lists for grants / manuscripts.
"""

from __future__ import annotations

from pathlib import Path

import typer

from elib.services.bibtex import documents_to_bibtex
from elib.services.db_manager import DatabaseManager

# ========================================================= #
# elib <list> command group                                 #
# ========================================================= #

list_app = typer.Typer(
    help="Manage named paper lists (grants, manuscripts) and export BibTeX.",
    no_args_is_help=True,
)


def _db(ctx: typer.Context) -> DatabaseManager:
    return DatabaseManager(ctx.obj["config"].database_path)


@list_app.command("create")
def list_create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Unique list name, e.g. R01-2026"),
    description: str | None = typer.Option(None, "--description", "-d"),
):
    """Create a new named paper list."""
    db = _db(ctx)
    try:
        pl = db.create_paper_list(name, description=description)
    except Exception as e:
        typer.echo(f"Error creating list: {e}", err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"Created list '{pl.name}' (id={pl.id})")


@list_app.command("rename")
def list_rename(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Current list name"),
    new_name: str = typer.Argument(..., help="New list name"),
    description: str | None = typer.Option(
        None,
        "--description",
        "-d",
        help="Also set description (use empty string to clear)",
    ),
):
    """Rename a paper list (membership preserved). Optionally update description."""
    db = _db(ctx)
    if db.get_paper_list(name=name) is None:
        typer.echo(f"List not found: {name}", err=True)
        raise typer.Exit(code=1)
    try:
        # Only pass description when user supplied -d so we don't wipe it
        kwargs: dict = {"name": name, "new_name": new_name}
        if description is not None:
            kwargs["description"] = description
        pl = db.rename_paper_list(**kwargs)
    except Exception as e:
        typer.echo(f"Error renaming list: {e}", err=True)
        raise typer.Exit(code=1) from e
    if pl is None:
        typer.echo("Rename failed.", err=True)
        raise typer.Exit(code=1)
    desc = f" — {pl.description}" if pl.description else ""
    typer.echo(f"Renamed '{name}' → '{pl.name}'{desc}")


@list_app.command("ls")
def list_ls(ctx: typer.Context):
    """List all named paper lists."""
    db = _db(ctx)
    lists = db.list_paper_lists()
    if not lists:
        typer.echo("No paper lists yet. Create one with: elib list create NAME")
        return
    for pl in lists:
        desc = f" — {pl.description}" if pl.description else ""
        typer.echo(f"  [{pl.id}] {pl.name}  ({pl.item_count} papers){desc}")


@list_app.command("show")
def list_show(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="List name"),
):
    """Show papers in a named list."""
    db = _db(ctx)
    pl = db.get_paper_list(name=name)
    if pl is None:
        typer.echo(f"List not found: {name}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"=== {pl.name} (id={pl.id}, {pl.item_count} papers) ===")
    if pl.description:
        typer.echo(pl.description)
    typer.echo("")

    items = db.get_list_items(list_name=name)
    if not items:
        typer.echo("  (empty)")
        return
    for i, item in enumerate(items, 1):
        d = item.document
        if d is None:
            typer.echo(f"  {i}. document_id={item.document_id}")
            continue
        year = d.publication_year or "?"
        doi = d.doi or "-"
        typer.echo(f"  {i}. [{d.id}] ({year}) {d.title[:80]}")
        typer.echo(f"      doi={doi}  pmid={d.pmid or '-'}  status={d.metadata_status.value}")
        if item.notes:
            typer.echo(f"      notes: {item.notes}")


@list_app.command("add")
def list_add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="List name"),
    doc_id: int | None = typer.Option(None, "--id", help="Document id"),
    doi: str | None = typer.Option(None, help="Document DOI"),
    notes: str | None = typer.Option(None, "--notes", "-n"),
):
    """Add a library document to a list (by --id or --doi)."""
    if doc_id is None and not doi:
        typer.echo("Provide --id or --doi", err=True)
        raise typer.Exit(code=1)

    db = _db(ctx)
    if db.get_paper_list(name=name) is None:
        typer.echo(f"List not found: {name}", err=True)
        raise typer.Exit(code=1)

    item = db.add_to_list(list_name=name, document_id=doc_id, doi=doi, notes=notes)
    if item is None:
        typer.echo("Document not found (check --id / --doi).", err=True)
        raise typer.Exit(code=1)

    title = item.document.title if item.document else str(item.document_id)
    typer.echo(f"Added to '{name}': {title[:70]}")


@list_app.command("remove")
def list_remove(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="List name"),
    doc_id: int | None = typer.Option(None, "--id", help="Document id"),
    doi: str | None = typer.Option(None, help="Document DOI"),
):
    """Remove a document from a list."""
    if doc_id is None and not doi:
        typer.echo("Provide --id or --doi", err=True)
        raise typer.Exit(code=1)

    db = _db(ctx)
    ok = db.remove_from_list(list_name=name, document_id=doc_id, doi=doi)
    if not ok:
        typer.echo("Nothing removed (list or document membership not found).", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Removed from '{name}'.")


@list_app.command("delete")
def list_delete(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="List name"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    hard: bool = typer.Option(
        False,
        "--hard",
        help="Permanently delete list + memberships (default is soft-delete).",
    ),
):
    """Soft-delete a list by default (hidden; restore with `elib list restore`).

    Documents always remain in the library.
    """
    db = _db(ctx)
    pl = db.get_paper_list(name=name, include_deleted=hard)
    if pl is None:
        typer.echo(f"List not found: {name}", err=True)
        raise typer.Exit(code=1)
    kind = "hard-delete" if hard else "soft-delete"
    if not yes:
        confirm = typer.confirm(f"{kind} list '{name}' ({pl.item_count} items)?")
        if not confirm:
            raise typer.Abort()
    ok = db.delete_paper_list(name=name, hard=hard)
    if not ok:
        typer.echo("Delete failed.", err=True)
        raise typer.Exit(code=1)
    if hard:
        typer.echo(f"Permanently deleted list '{name}'.")
    else:
        typer.echo(f"Soft-deleted list '{name}' (restore: elib list restore {name!r}).")


@list_app.command("restore")
def list_restore(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="List name"),
):
    """Restore a soft-deleted list."""
    db = _db(ctx)
    if not db.restore_paper_list(name=name):
        typer.echo(f"Could not restore list (not found or not deleted): {name}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Restored list '{name}'.")


@list_app.command("export")
def list_export(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="List name"),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write to file. Default: ~/elibrary/exports/<name>.bib (use '-' for stdout)",
    ),
    format: str = typer.Option("bibtex", "--format", "-f", help="Export format (bibtex)"),
):
    """Export a list to BibTeX."""
    if format.lower() not in ("bibtex", "bib"):
        typer.echo(f"Unsupported format: {format} (only bibtex for now)", err=True)
        raise typer.Exit(code=1)

    db = _db(ctx)
    config = ctx.obj["config"]
    pl = db.get_paper_list(name=name)
    if pl is None:
        typer.echo(f"List not found: {name}", err=True)
        raise typer.Exit(code=1)

    items = db.get_list_items(list_name=name)
    docs = [i.document for i in items if i.document is not None]
    bib = documents_to_bibtex(docs)

    if output is not None and str(output) == "-":
        typer.echo(bib)
        return

    if output is None:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
        out_dir = Path(config.exports_directory).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        output = out_dir / f"{safe}.bib"

    output = Path(output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(bib, encoding="utf-8")
    typer.echo(f"Wrote {len(docs)} entries to {output}")
