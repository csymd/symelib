"""
The elib <search> command implementation, with access to local and PubMed databases.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

import typer

from symworx_elibrary.models.metadata import (
    SearchField,
    SearchQuery,
    SortBy,
    SortOrder,
    import_window_bounds,
)
from symworx_elibrary.services.db_manager import DatabaseManager
from symworx_elibrary.services.ncbi_client import NCBIClient

# ========================================================= #
# Enums and Constants                                    #
# ======================================================== #


class SearchSource(str, Enum):
    LOCAL = "local"
    PUBMED = "pubmed"
    BOTH = "both"


class AddedSince(str, Enum):
    """Relative import windows for ``--added-since`` (no ``all``; omit the flag)."""

    today = "today"
    days_7 = "7d"
    days_30 = "30d"


class ExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"
    XML = "xml"


def _parse_iso_date(value: str | None) -> date | None:
    """Parse YYYY-MM-DD for Typer (datetime.date is not a supported option type)."""
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid date {value!r}; use YYYY-MM-DD") from exc


# ========================================================= #
# elib <search> command                                     #
# ========================================================= #


def search(
    ctx: typer.Context,
    text: str | None = typer.Argument(
        None,
        help="Search text (prefix match by default: cardio → cardiovascular)",
    ),
    author: str = typer.Option(None, help="Filter by author name (substring)."),
    field: SearchField = typer.Option(
        SearchField.all,
        "--field",
        "-f",
        help="Scope free-text: all | title | keywords | author | abstract",
    ),
    year_from: int = typer.Option(None, help="Filter by publication year (start)."),
    year_to: int = typer.Option(None, help="Filter by publication year (end)."),
    added_from: str | None = typer.Option(
        None,
        "--added-from",
        help="Imported on or after this date (YYYY-MM-DD).",
    ),
    added_to: str | None = typer.Option(
        None,
        "--added-to",
        help="Imported on or before this date (YYYY-MM-DD).",
    ),
    added_since: AddedSince | None = typer.Option(
        None,
        "--added-since",
        help="Relative import window: today | 7d | 30d (sets --added-from/--added-to).",
    ),
    journal: str = typer.Option(None, help="Filter by journal."),
    doi: str = typer.Option(None, help="Filter by DOI."),
    pmid: str = typer.Option(None, help="Filter by PMID."),
    keywords: list[str] = typer.Option(None, "--keyword", help="Add keyword filter."),
    sort_by: SortBy = typer.Option(
        SortBy.relevance,
        "--sort-by",
        help="Sort: relevance | year | author | title | added_date",
    ),
    sort_order: SortOrder = typer.Option(
        SortOrder.desc,
        "--sort-order",
        help="asc | desc",
    ),
    limit: int = typer.Option(
        20,
        help="Limit the number of results (default=20).",
        show_default=True,
    ),
    offset: int = typer.Option(
        0,
        help="Offset for pagination.",
        show_default=True,
    ),
    source: SearchSource = typer.Option(SearchSource.LOCAL),
    export_format: ExportFormat = typer.Option(ExportFormat.JSON),
    as_json: bool = typer.Option(True, help="Output results in JSON format."),
):
    """
    Search your local library and/or PubMed.

    Free-text uses **prefix matching** (``cardio`` matches ``cardiovascular``).
    Scope with ``--field title|keywords|author|abstract|all`` (default: all).

    Examples:

        elib search cardio
        elib search cardio --field title
        elib search Smith --field author
        elib search --sort-by year --sort-order desc
        elib search --sort-by author
        elib search --added-since 7d
        elib search --added-from 2026-08-01 --added-to 2026-08-28
        elib search "heart rate" --source pubmed
    """
    config = ctx.obj["config"]
    _ = ctx.obj["logger"]

    # Initialize results
    local_results = []
    pubmed_results = []
    keywords = keywords or []

    # === Search Local Library ===
    if source in ["local", "both"]:
        db_manager = DatabaseManager(config.database_path)

        since_from, since_to = (None, None)
        if added_since is not None:
            since_from, since_to = import_window_bounds(added_since.value)
        parsed_from = _parse_iso_date(added_from)
        parsed_to = _parse_iso_date(added_to)
        if parsed_from is not None and parsed_to is not None and parsed_from > parsed_to:
            typer.echo("Error: --added-from must be on or before --added-to", err=True)
            raise typer.Exit(code=1)
        query = SearchQuery(
            text=text,
            author=author,
            year_from=year_from,
            year_to=year_to,
            journal=journal,
            doi=doi,
            pmid=pmid,
            keywords=list(keywords),
            search_field=field,
            sort_by=sort_by,
            sort_order=sort_order,
            added_from=since_from if since_from is not None else parsed_from,
            added_to=since_to if since_to is not None else parsed_to,
            limit=limit,
            offset=offset,
        )

        local_results = db_manager.search(query)

    # === Serach PubMed ===
    if source in ["pubmed", "both"]:
        # local import for serach service (and avoiding circular dependency)

        if not text:
            typer.echo("Error: --text required for PubMed search")
            return

        ncbi_client = NCBIClient(email=config.ncbi_email, api_key=config.ncbi_api_key)

        # Search PubMed
        pmids = ncbi_client.search_pubmed(
            query=text, max_results=limit, year_from=year_from, year_to=year_to
        )

        # Fetch full references
        if pmids:
            references = ncbi_client.fetch_references(pmids)

            # Check which are already in library
            db_manager = DatabaseManager(config.database_path)
            for ref in references:
                in_library = False
                if ref.doi:
                    existing = db_manager.get_by_doi(ref.doi) if source == "both" else None
                    in_library = existing is not None

                pubmed_results.append({"reference": ref, "in_library": in_library})

    # === Display results ===
    if as_json:
        _display_json_results(local_results, pubmed_results, source)
    else:
        _display_text_results(local_results, pubmed_results, source)


def _display_text_results(local_results, pubmed_results, source):
    """Display search results in text format."""

    if source in ["local", "both"] and local_results:
        typer.echo(f"\n=== Local Library ({len(local_results)} results) ===\n")

        for i, r in enumerate(local_results, 1):
            m = r.metadata
            typer.echo(f"{i}. {m.title}")
            typer.echo(f"   Authors: {m.authors_json[:120]}...")
            typer.echo(f"   Journal: {m.journal} ({m.publication_year})")
            typer.echo(f"   DOI: {m.doi}  PMID: {m.pmid or '-'}")
            typer.echo(f"   📄 File: {m.filename}")
            if m.added_date:
                typer.echo(f"   Imported: {m.added_date.date().isoformat()}")
            typer.echo("")

    if source in ["pubmed", "both"] and pubmed_results:
        typer.echo(f"\n=== PubMed Results ({len(pubmed_results)} results) ===\n")

        for i, item in enumerate(pubmed_results, 1):
            ref = item["reference"]
            in_lib = item["in_library"]

            # Format authors
            author_str = ", ".join([a.last_name for a in ref.authors[:3]])
            if len(ref.authors) > 3:
                author_str += ", et al."

            typer.echo(f"{i}. {ref.title}")
            typer.echo(f"   Authors: {author_str}")
            typer.echo(f"   Journal: {ref.journal.title} ({ref.publication_year()})")
            typer.echo(f"   DOI: {ref.doi}  PMID: {ref.pmid}")

            if in_lib:
                typer.echo("   ✓ Already in your library")
            else:
                typer.echo("   + Not in library")

            typer.echo("")

    if not local_results and not pubmed_results:
        typer.echo("No results found.")


def _display_json_results(local_results, pubmed_results, source):
    """Display search results in JSON format."""
    import json

    output = {
        "source": source,
        "local_count": len(local_results),
        "pubmed_count": len(pubmed_results),
        "local_results": [],
        "pubmed_results": [],
    }

    # Local results
    for r in local_results:
        m = r.metadata
        output["local_results"].append(
            {
                "title": m.title,
                "authors": m.authors_json,
                "journal": m.journal,
                "year": m.publication_year,
                "doi": m.doi,
                "pmid": m.pmid,
                "filename": m.filename,
                "file_path": m.file_path,
                "added_date": m.added_date.isoformat() if m.added_date else None,
                "in_library": True,
            }
        )

    # PubMed results
    for item in pubmed_results:
        ref = item["reference"]
        output["pubmed_results"].append(
            {
                "title": ref.title,
                "authors": [a.dict() for a in ref.authors],
                "journal": ref.journal.dict(),
                "year": ref.publication_year(),
                "doi": ref.doi,
                "pmid": ref.pmid,
                "abstract": ref.abstract,
                "keywords": ref.keywords,
                "in_library": item["in_library"],
            }
        )

    typer.echo(json.dumps(output, indent=2))
