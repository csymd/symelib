"""
src/elib/cli.py
"""
import click
from pathlib import Path

from .services.pdf_processor import PDFProcessor
from .services.ncbi_client import NCBIClient
from .services.db_manager import DatabaseManager
from .services.file_manager import FileManager
from .models.metadata import SearchQuery
from .utils.config import Config

# ========================================================= #
# Command-Line Interface (CLI) for elib                      #
# ========================================================= #

@click.group()
@click.pass_context
def cli(ctx):
    """elib - Electronic Library Management System"""
    ctx.ensure_object(dict)
    config = Config.load()
    ctx.obj['config'] = config

@cli.command()
@click.argument('source_dir', type=click.Path(exists=True))
@click.option('--target-dir', type=click.Path(), default=None)
@click.pass_context
def process(ctx, source_dir, target_dir):
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
@click.option('--text', help='Search in title, abstract, keywords')
@click.option('--author', help='Filter by author name')
@click.option('--year-from', type=int, help='Publication year from')
@click.option('--year-to', type=int, help='Publication year to')
@click.option('--limit', type=int, default=20, help='Number of results')
@click.pass_context
def search(ctx, text, author, year_from, year_to, limit):
    """Search the library"""
    config = ctx.obj['config']
    db_manager = DatabaseManager(config.database_path)
    
    query = SearchQuery(
        text=text,
        author=author,
        year_from=year_from,
        year_to=year_to,
        limit=limit
    )
    
    results = db_manager.search(query)
    
    click.echo(f"Found {len(results)} results:\n")
    
    for i, result in enumerate(results, 1):
        meta = result.metadata
        click.echo(f"{i}. {meta.title}")
        click.echo(f"   Authors: {meta.authors_json[:100]}...")
        click.echo(f"   Journal: {meta.journal} ({meta.publication_year})")
        click.echo(f"   File: {meta.filename}")
        click.echo(f"   DOI: {meta.doi}\n")

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

if __name__ == '__main__':
    cli()
