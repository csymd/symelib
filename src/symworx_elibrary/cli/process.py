"""
The elib <process> command to process PDFs into the library.
"""

from __future__ import annotations

from pathlib import Path

import typer

from symworx_elibrary.services.db_manager import DatabaseManager
from symworx_elibrary.services.file_manager import FileManager
from symworx_elibrary.services.ncbi_client import NCBIClient
from symworx_elibrary.services.pdf_processor import PDFProcessor
from symworx_elibrary.utils.rate_limiter import configure_process_delay

# ========================================================= #
# elib <process> command                                    #
# ========================================================= #


def process(
    source_dir: Path | None = typer.Argument(
        None,
        help="Directory containing PDFs to process "
        "(default: cart_directory from config, usually ~/elibrary/cart)",
    ),
    target_dir: Path | None = typer.Option(
        None, help="Target directory for processed files (default: ~/elibrary/library)"
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        help="Process at most N PDFs (useful for large cart/ folders).",
    ),
    delay: float | None = typer.Option(
        None,
        "--delay",
        help="Min seconds between NCBI/Crossref HTTP calls (default: 0.5 without "
        "API key, 0.15 with key). Increase if you hit 429s, e.g. --delay 1.0",
    ),
    use_cli: bool = typer.Option(False, help="Use CLI tools instead of HTTP API"),
    verbose: int = typer.Option(0, "--verbose", "-v", help="Increase verbosity"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Quiet mode"),
    ctx: typer.Context = typer.Option(None, hidden=True),
):
    """
    Process PDFs into the library (metadata + copy into target_directory).

    Defaults to your AWS-synced cart inbox:

        elib process                  # ~/elibrary/cart → ~/elibrary/library
        elib process --limit 20       # first 20 PDFs only
        elib process --delay 1.0      # slower, fewer 429s
        elib process /path/to/pdfs

    NCBI rate limits: ~3 req/s without API key, ~10/s with key. A 429 triggers
    automatic backoff; prefer setting ncbi_api_key in config.yaml if you have one.
    """
    config = ctx.obj["config"]
    logger = ctx.obj["logger"]

    src = source_dir if source_dir is not None else Path(config.cart_directory)
    src = src.expanduser()
    if not src.exists():
        typer.echo(f"Source directory does not exist: {src}", err=True)
        typer.echo(
            "Set cart_directory in ~/elibrary/config.yaml or pass a path explicitly.",
            err=True,
        )
        raise typer.Exit(code=1)

    target_path = (target_dir if target_dir else config.target_directory).expanduser()

    # Rate limits: explicit --delay wins; else derived from API key presence
    if delay is not None:
        configure_process_delay(delay)
        typer.echo(f"HTTP delay between remote calls: {delay:.2f}s")
    elif not config.ncbi_api_key:
        configure_process_delay(0.5)
        typer.echo(
            "No ncbi_api_key set — using 0.5s between NCBI/Crossref calls "
            "(add key for ~0.15s; use --delay to override)."
        )

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

    typer.echo(f"Source (cart/inbox): {src}")
    typer.echo(f"Target (library):    {target_path}")
    typer.echo(f"Database:            {config.database_path}")
    logger.info(f"Processing PDFs from: {src}")

    if limit is not None:
        # Temporary: scan then process only first N
        docs = pdf_processor.scan_directory(src)[:limit]
        processed = []
        errors = []
        for doc in docs:
            try:
                result = file_manager.process_single_document(doc)
                if result:
                    processed.append(result)
            except Exception as e:
                errors.append(f"{doc.file_path}: {e!s}")
    else:
        processed, errors = file_manager.process_directory(src)

    typer.echo(f"\nProcessed {len(processed)} documents successfully")
    logger.info(f"Processed {len(processed)} documents successfully")

    if errors:
        typer.echo(f"\nErrors ({len(errors)}):")
        logger.error(f"Errors ({len(errors)}):")
        for error in errors:
            typer.echo(f"  - {error}")
