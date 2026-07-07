"""
The elib <process> command to process PDFs into the library.
"""

from __future__ import annotations

from pathlib import Path

import typer

from elib.services.db_manager import DatabaseManager
from elib.services.file_manager import FileManager
from elib.services.ncbi_client import NCBIClient
from elib.services.pdf_processor import PDFProcessor

# ========================================================= #
# elib <process> command                                    #
# ========================================================= #


def process(
    source_dir: Path = typer.Argument(
        ..., exists=True, help="Directory containing PDFs to process"
    ),
    target_dir: Path = typer.Option(None, help="Target directory for processed files"),
    use_cli: bool = typer.Option(False, help="Use CLI tools instead of HTTP API"),
    verbose: int = typer.Option(0, "--verbose", "-v", help="Increase verbosity"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Quiet mode"),
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    """Process PDFs in SOURCE_DIR."""
    config = ctx.obj["config"]
    logger = ctx.obj["logger"]

    target_path = target_dir if target_dir else config.target_directory

    # Initialize services
    pdf_processor = PDFProcessor()
    ncbi_client = NCBIClient(email=config.ncbi_email, api_key=config.ncbi_api_key)
    db_manager = DatabaseManager(config.database_path)
    file_manager = FileManager(
        pdf_processor=pdf_processor,
        ncbi_client=ncbi_client,
        db_manager=db_manager,
        target_directory=target_path,
    )

    # Process directory
    typer.echo(f"Processing PDFs from: {source_dir}")
    typer.echo(f"Target directory: {target_path}; Source directory: {source_dir}")
    logger.info(f"Processing PDFs from: {source_dir}")
    logger.debug(f"Source directory: {source_dir}")
    logger.debug(f"Target directory: {target_path}")

    processed, errors = file_manager.process_directory(source_dir)

    typer.echo(f"\nProcessed {len(processed)} documents successfully")
    logger.info(f"Processed {len(processed)} documents successfully")

    if errors:
        typer.echo(f"\nErrors ({len(errors)}):")
        logger.error(f"Errors ({len(errors)}):")
        for error in errors:
            typer.echo(f"  - {error}")
