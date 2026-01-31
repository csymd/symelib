"""
src/elib/cli/search.py

The elib <search> command implementation, with access to local and PubMed databases.
"""
from __future__ import annotations

import typer
from pathlib import Path

from elib.models.metadata import SearchQuery
from elib.services.db_manager import DatabaseManager
from elib.services.ncbi_client import NCBIClient
from elib.services.file_manager import FileManager
from elib.services.pdf_processor import PDFProcessor

# ========================================================= #
# elib <search> command                                     #
# ========================================================= #

@app.command()
def search(
        text: str = typer.Option(
            None,
            description='Full-text serach (title, abstract, keywords)'
        ),
        author: str = typer.Option(
            None,
            description='Filter by author name.'
        ),
        year_from: int = typer.Option(
            None,
            description='Filter by publication year (start).'
        ),
        year_to: int = typer.Option(
            None,
            description='Filter by publication year (end).'
        ),
        journal: str = typer.Option(
            None,
            description='Filter by journal.'
        ),
        doi: str = typer.Option(
            None,
            description='Filter by DOI.'
        ),
        pmid: str = typer.Option(
            None,
            description='Filter by PMID.'
        ),
        keywords: list[str] = typer.Option(
            None,
           '--keyword',
           help='Add keyword filter.'
        ),
        sort_by: str = typer.Option(
            'relevance',
           help='Sort results by specific field.',
           case_sensitive=False,
           show_choices=True,
           choices=['relevance', 'year', 'title', 'added_date'],
        ),
        sort_order: str = typer.Option(
            'desc',
            help='Sort order for results.',
            case_sensitive=False,
            show_choices=True,
            choices=['asc', 'desc'],
        ),
        limit: int = typer.Option(
            20,
            help='Limit the number of results (default=20).',
            show_default=True,
        ),
        offset: int = typer.Option(
            0,
            help='Offset for pagintation.',
            show_default=True,
        ),
        source: str = typer.Option(
            'local',
            help='Search source: local, PubMed, or both.',
            case_sensitive=False,
            show_choices=True,
            choices=['local', 'pubmed', 'both']
        ),
        export_format: str = typer.Option(
            None,
            description=''
        ),
    ):
    """
    Search your local library and/or PubMed.

    Examples:

        # Search local library only
        elib search --text "heart rate recovery"

        # Search PubMed only
        elib search --text "heart rate recovery" --source pubmed

        # Search both
        elib search --text "heart rate recovery" --source both
    """
    config = typer.Context.obj['config']
    logger = typer.Context.obj['logger']

    # Initialize results
    local_results = []
    pubmed_results = []

    # === Search Local Library ===
   if source in ['local', 'both']:
        db_manager = DatabaseManager(config.database_path)

        query = SearchQuery(
            text=text,
            author=author,
            year_from=year_from,
            year_to=year_to,
            journal=journal,
            doi=doi,
            pmid=pmid,
            keywords=list(keywords),
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset
        )

        local_results = db_manager.search(query)

    # === Serach PubMed ===
    if source in ['pubmed', 'both']:
        # local import for serach service (and avoiding circular dependency)
        from elib.services.search_pubmed import PubMedSearchService

        if not text:
            typer.echo("Error: --text required for PubMed search")
            return

        ncbi_client = NCBIClient(
            email=config.ncbi_email,
            api_key=config.ncbi_api_key
        )

        # Search PubMed
        pmids = ncbi_client.search_pubmed(
            query=text,
            max_results=limit,
            year_from=year_from,
            year_to=year_to
        )

        # Fetch full references
        if pmids:
            references = ncbi_client.fetch_references(pmids)

            # Check which are already in library
            db_manager = DatabaseManager(config.database_path)
            for ref in references:
                in_library = False
                if ref.doi:
                    existing = db_manager.get_by_doi(ref.doi) if source == 'both' else None
                    in_library = existing is not None

                pubmed_results.append({
                    'reference': ref,
                    'in_library': in_library
                })

    # === Display results ===
    if as_json:
        _display_json_results(local_results, pubmed_results, source)
    else:
        _display_text_results(local_results, pubmed_results, source)




# def search(ctx, text, author, year_from, year_to, journal, doi, pmid,
#            keywords, sort_by, sort_order, limit, offset, source, as_json):
#     """Search your local library and/or PubMed.
    
#     Examples:
    
#         # Search local library only
#         elib search --text "heart rate recovery"
        
#         # Search PubMed only
#         elib search --text "heart rate recovery" --source pubmed
        
#         # Search both
#         elib search --text "heart rate recovery" --source both
#     """
#     config = ctx.obj['config']
    
#     local_results = []
#     pubmed_results = []
    
#     # Search local library
#     if source in ['local', 'both']:
#         db_manager = DatabaseManager(config.database_path)
        
#         query = SearchQuery(
#             text=text,
#             author=author,
#             year_from=year_from,
#             year_to=year_to,
#             journal=journal,
#             doi=doi,
#             pmid=pmid,
#             keywords=list(keywords),
#             sort_by=sort_by,
#             sort_order=sort_order,
#             limit=limit,
#             offset=offset
#         )
        
#         local_results = db_manager.search(query)
    
#     # Search PubMed
#     if source in ['pubmed', 'both']:
#         from elib.services.search_pubmed import PubMedSearchService
        
#         if not text:
#             click.echo("Error: --text required for PubMed search")
#             return
        
#         pubmed_service = PubMedSearchService(
#             email=config.ncbi_email,
#             api_key=config.ncbi_api_key
#         )
        
#         # Search PubMed
#         pmids = pubmed_service.search(
#             query=text,
#             max_results=limit,
#             year_from=year_from,
#             year_to=year_to
#         )
        
#         # Fetch full references
#         if pmids:
#             references = pubmed_service.fetch_references(pmids)
            
#             # Check which are already in library
#             for ref in references:
#                 in_library = False
#                 if ref.doi:
#                     existing = db_manager.get_by_doi(ref.doi) if source == 'both' else None
#                     in_library = existing is not None
                
#                 pubmed_results.append({
#                     'reference': ref,
#                     'in_library': in_library
#                 })
    
#     # Display results
#     if as_json:
#         _display_json_results(local_results, pubmed_results, source)
#     else:
#         _display_text_results(local_results, pubmed_results, source)


def _display_text_results(local_results, pubmed_results, source):
    """Display search results in text format."""
    
    if source in ['local', 'both'] and local_results:
        typer.echo(f"\n=== Local Library ({len(local_results)} results) ===\n")
        
        for i, r in enumerate(local_results, 1):
            m = r.metadata
            typer.echo(f"{i}. {m.title}")
            typer.echo(f"   Authors: {m.authors_json[:120]}...")
            typer.echo(f"   Journal: {m.journal} ({m.publication_year})")
            typer.echo(f"   DOI: {m.doi}  PMID: {m.pmid or '-'}")
            typer.echo(f"   📄 File: {m.filename}")
            typer.echo("")
    
    if source in ['pubmed', 'both'] and pubmed_results:
        typer.echo(f"\n=== PubMed Results ({len(pubmed_results)} results) ===\n")
        
        for i, item in enumerate(pubmed_results, 1):
            ref = item['reference']
            in_lib = item['in_library']
            
            # Format authors
            author_str = ", ".join([a.last_name for a in ref.authors[:3]])
            if len(ref.authors) > 3:
                author_str += ", et al."
            
            typer.echo(f"{i}. {ref.title}")
            typer.echo(f"   Authors: {author_str}")
            typer.echo(f"   Journal: {ref.journal.title} ({ref.publication_year()})")
            typer.echo(f"   DOI: {ref.doi}  PMID: {ref.pmid}")
            
            if in_lib:
                typer.echo(f"   ✓ Already in your library")
            else:
                typer.echo(f"   + Not in library")
            
            typer.echo("")
    
    if not local_results and not pubmed_results:
        typer.echo("No results found.")


def _display_json_results(local_results, pubmed_results, source):
    """Display search results in JSON format."""
    import json
    
    output = {
        'source': source,
        'local_count': len(local_results),
        'pubmed_count': len(pubmed_results),
        'local_results': [],
        'pubmed_results': []
    }
    
    # Local results
    for r in local_results:
        m = r.metadata
        output['local_results'].append({
            'title': m.title,
            'authors': m.authors_json,
            'journal': m.journal,
            'year': m.publication_year,
            'doi': m.doi,
            'pmid': m.pmid,
            'filename': m.filename,
            'file_path': m.file_path,
            'in_library': True
        })
    
    # PubMed results
    for item in pubmed_results:
        ref = item['reference']
        output['pubmed_results'].append({
            'title': ref.title,
            'authors': [a.dict() for a in ref.authors],
            'journal': ref.journal.dict(),
            'year': ref.publication_year(),
            'doi': ref.doi,
            'pmid': ref.pmid,
            'abstract': ref.abstract,
            'keywords': ref.keywords,
            'in_library': item['in_library']
        })
    
    typer.echo(json.dumps(output, indent=2))
