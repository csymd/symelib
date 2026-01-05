"""
src/elib/cli.py
"""
import os
import json
import click
from pathlib import Path

from elib.models.metadata import SearchQuery
from elib.services.db_manager import DatabaseManager
from elib.services.ncbi_client import NCBIClient
from elib.services.file_manager import FileManager
from elib.services.pdf_processor import PDFProcessor
from elib.services.search_pubmed import PubMedSearchService
from elib.utils.config import Config
from elib.utils.logging import get_shared_logger

# ========================================================= #
# Command-Line Interface (CLI) for elib                      #
# ========================================================= #

@click.group()
@click.option('-v', '--verbose', count=True, 
              help='Increase verbosity: -v (INFO), -vv (DEBUG), -vvv (DEBUG with details)')
@click.option('-q', '--quiet', is_flag=True, 
              help='Quiet mode: only show ERROR and CRITICAL messages')
@click.option('--log-level',
              type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], case_sensitive=False),
              help='Explicitly set log level (overrides -v/-q flags)')
@click.pass_context
def cli(ctx, verbose, quiet, log_level):
    """elib - Electronic Library Management System"""
    ctx.ensure_object(dict)

    # Load Config
    config = Config.load()
    ctx.obj['config'] = config

    # Determine log level
    if log_level:
        level = log_level.upper()
    elif quiet:
        level = 'ERROR'
    elif verbose >= 3:
        level = 'DEBUG'
    elif verbose == 2:
        level = 'DEBUG'
    elif verbose == 1:
        level = 'INFO'
    elif os.getenv('LOG_LEVEL'):
        level = os.getenv('LOG_LEVEL').upper()
    elif os.getenv('LOG_ENV'):
        env_to_level = {
            'PROD': 'ERROR',
            'STAGING': 'WARNING',
            'DEV': 'DEBUG',
            'TEST': 'INFO'
        }
        level = env_to_level.get(os.getenv('LOG_ENV', '').upper(), 'INFO')
    else:
        level = 'INFO'

    # Initialize Logger
    logger = get_shared_logger(name='elib', level=level)
    logger.level = level
    ctx.obj['logger'] = logger
    
    logger.debug('CLI initialize',
               log_level=level,
               verbose_count=verbose,
               quiet=quiet,
               explicit_log_level=log_level)


@cli.command()
@click.argument('source_dir', type=click.Path(exists=True))
@click.option('--target-dir', type=click.Path(), default=None)
@click.option('--use-cli', is_flag=True, help='Use CLI tools instead of HTTP API')
@click.pass_context
def process(ctx, source_dir, target_dir, use_cli):
    """Process PDFs in SOURCE_DIR"""
    config = ctx.obj['config']
    
    source_path = Path(source_dir)
    target_path = Path(target_dir) if target_dir else config.target_directory
    
    # Initialize services
    pdf_processor = PDFProcessor()
    ncbi_client = NCBIClient(email=config.ncbi_email, api_key=config.ncbi_api_key)
    db_manager = DatabaseManager(config.database_path)
    file_manager = FileManager(
        pdf_processor=pdf_processor,
        ncbi_client=ncbi_client,
        db_manager=db_manager,
        target_directory=target_path
    )
    
    # Process directory
    click.echo(f"Processing PDFs from: {source_path}")
    click.echo(f"Target directory: {target_path}")
    
    processed, errors = file_manager.process_directory(source_path)
    
    click.echo(f"\nProcessed {len(processed)} documents successfully")
    
    if errors:
        click.echo(f"\nErrors ({len(errors)}):")
        for error in errors:
            click.echo(f"  - {error}")

            
@cli.command()
@click.option('--text', help='Full-text search in title, abstract, keywords')
@click.option('--author', help='Filter by author name')
@click.option('--year-from', type=int, help='Publication year from')
@click.option('--year-to', type=int, help='Publication year to')
@click.option('--journal', help='Filter by journal name')
@click.option('--doi', help='Filter by DOI')
@click.option('--pmid', help='Filter by PMID')
@click.option('--keyword', 'keywords', multiple=True, help='Add keyword filter (repeatable)')
@click.option('--sort-by', type=click.Choice(['relevance', 'year', 'title', 'added_date']),
              default='relevance', show_default=True)
@click.option('--sort-order', type=click.Choice(['asc', 'desc']),
              default='desc', show_default=True)
@click.option('--limit', type=int, default=20, show_default=True)
@click.option('--offset', type=int, default=0, show_default=True)
@click.option('--source', type=click.Choice(['local', 'pubmed', 'both']),
              default='local', show_default=True,
              help='Search source: local library, PubMed, or both')
@click.option('--json', 'as_json', is_flag=True, help='Return results as JSON')
@click.pass_context
def search(ctx, text, author, year_from, year_to, journal, doi, pmid,
           keywords, sort_by, sort_order, limit, offset, source, as_json):
    """Search your local library and/or PubMed.
    
    Examples:
    
        # Search local library only
        elib search --text "heart rate recovery"
        
        # Search PubMed only
        elib search --text "heart rate recovery" --source pubmed
        
        # Search both
        elib search --text "heart rate recovery" --source both
    """
    config = ctx.obj['config']
    
    local_results = []
    pubmed_results = []
    
    # Search local library
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
    
    # Search PubMed
    if source in ['pubmed', 'both']:
        from elib.services.search_pubmed import PubMedSearchService
        
        if not text:
            click.echo("Error: --text required for PubMed search")
            return
        
        pubmed_service = PubMedSearchService(
            email=config.ncbi_email,
            api_key=config.ncbi_api_key
        )
        
        # Search PubMed
        pmids = pubmed_service.search(
            query=text,
            max_results=limit,
            year_from=year_from,
            year_to=year_to
        )
        
        # Fetch full references
        if pmids:
            references = pubmed_service.fetch_references(pmids)
            
            # Check which are already in library
            for ref in references:
                in_library = False
                if ref.doi:
                    existing = db_manager.get_by_doi(ref.doi) if source == 'both' else None
                    in_library = existing is not None
                
                pubmed_results.append({
                    'reference': ref,
                    'in_library': in_library
                })
    
    # Display results
    if as_json:
        _display_json_results(local_results, pubmed_results, source)
    else:
        _display_text_results(local_results, pubmed_results, source)


def _display_text_results(local_results, pubmed_results, source):
    """Display search results in text format."""
    
    if source in ['local', 'both'] and local_results:
        click.echo(f"\n=== Local Library ({len(local_results)} results) ===\n")
        
        for i, r in enumerate(local_results, 1):
            m = r.metadata
            click.echo(f"{i}. {m.title}")
            click.echo(f"   Authors: {m.authors_json[:120]}...")
            click.echo(f"   Journal: {m.journal} ({m.publication_year})")
            click.echo(f"   DOI: {m.doi}  PMID: {m.pmid or '-'}")
            click.echo(f"   📄 File: {m.filename}")
            click.echo("")
    
    if source in ['pubmed', 'both'] and pubmed_results:
        click.echo(f"\n=== PubMed Results ({len(pubmed_results)} results) ===\n")
        
        for i, item in enumerate(pubmed_results, 1):
            ref = item['reference']
            in_lib = item['in_library']
            
            # Format authors
            author_str = ", ".join([a.last_name for a in ref.authors[:3]])
            if len(ref.authors) > 3:
                author_str += ", et al."
            
            click.echo(f"{i}. {ref.title}")
            click.echo(f"   Authors: {author_str}")
            click.echo(f"   Journal: {ref.journal.title} ({ref.publication_year()})")
            click.echo(f"   DOI: {ref.doi}  PMID: {ref.pmid}")
            
            if in_lib:
                click.echo(f"   ✓ Already in your library")
            else:
                click.echo(f"   + Not in library")
            
            click.echo("")
    
    if not local_results and not pubmed_results:
        click.echo("No results found.")


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
    
    click.echo(json.dumps(output, indent=2))

        
@cli.command()
@click.pass_context
def stats(ctx):
    """Show library statistics"""
    config = ctx.obj['config']
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
    
    click.echo(f"Total documents: {total}")
    click.echo(f"Synced to S3: {synced}")
    click.echo(f"\nDocuments by year:")
    for row in years:
        click.echo(f"  {row['publication_year']}: {row['count']}")


@cli.command()
@click.pass_context
def rebuild_index(ctx):
    """Rebuild the full-text search index."""
    config = ctx.obj['config']
    db_manager = DatabaseManager(config.database_path)
    
    click.echo("Rebuilding FTS index...")
    count = db_manager.rebuild_fts_index()
    click.echo(f"✓ Rebuilt FTS index for {count} documents")

    
if __name__ == '__main__':
    cli()
