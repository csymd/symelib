"""
The elib <process> command to process PDFs into the library.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from symworx_elibrary.services.db_manager import DatabaseManager
from symworx_elibrary.services.file_manager import FileManager
from symworx_elibrary.services.ncbi_client import NCBIClient
from symworx_elibrary.services.pdf_processor import PDFProcessor
from symworx_elibrary.utils.rate_limiter import configure_process_delay

if TYPE_CHECKING:
    from symworx_elibrary.utils.config import Config

# ========================================================= #
# elib <process> command                                    #
# ========================================================= #


class ProcessFrom(str, Enum):
    """Configured inboxes when no explicit path is given."""

    tmp = "tmp"
    cart = "cart"
    all = "all"


def resolve_process_sources(
    *,
    config: Config,
    source_dir: Path | None = None,
    from_inbox: ProcessFrom = ProcessFrom.all,
) -> list[Path]:
    """Ordered unique ingest directories (tmp before cart for ``all``).

    An explicit ``source_dir`` is the only source (``--from`` is ignored).
    Missing directories are still returned; the command skips them later.
    """
    if source_dir is not None:
        return [Path(source_dir).expanduser()]

    ordered: list[Path] = []
    if from_inbox in (ProcessFrom.tmp, ProcessFrom.all):
        ordered.append(Path(config.temp_directory).expanduser())
    if from_inbox in (ProcessFrom.cart, ProcessFrom.all):
        ordered.append(Path(config.cart_directory).expanduser())

    unique: list[Path] = []
    seen: set[str] = set()
    for path in ordered:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def process(
    source_dir: Path | None = typer.Argument(
        None,
        help="Directory containing PDFs to process. Default: tmp then cart (see --from).",
    ),
    target_dir: Path | None = typer.Option(
        None, help="Target directory for processed files (default: ~/elibrary/library)"
    ),
    from_inbox: ProcessFrom = typer.Option(
        ProcessFrom.all,
        "--from",
        help="When no path is given: tmp, cart, or all (tmp then cart). "
        "Ignored if a path is passed.",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        help="Process at most N PDFs across the inbox sequence (tmp first, then cart).",
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

    Default inbox sequence (when no path is given) is tmp then cart:

        elib process                  # ~/elibrary/tmp then ~/elibrary/cart
        elib process --from tmp       # ~/elibrary/tmp only
        elib process --from cart      # ~/elibrary/cart only
        elib process --limit 20       # first 20 PDFs across that sequence
        elib process --delay 1.0      # slower, fewer 429s
        elib process /path/to/pdfs

    Already-imported source files are skipped (matched on source_path / DOI).
    NCBI rate limits: ~3 req/s without API key, ~10/s with key. A 429 triggers
    automatic backoff; prefer setting ncbi_api_key in config.yaml if you have one.
    """
    config = ctx.obj["config"]
    logger = ctx.obj["logger"]

    sources = resolve_process_sources(
        config=config,
        source_dir=source_dir,
        from_inbox=from_inbox,
    )
    existing = [path for path in sources if path.exists()]
    missing = [path for path in sources if not path.exists()]

    if source_dir is not None and not existing:
        typer.echo(f"Source directory does not exist: {sources[0]}", err=True)
        typer.echo(
            "Set temp_directory / cart_directory in ~/elibrary/config.yaml "
            "or pass a path explicitly.",
            err=True,
        )
        raise typer.Exit(code=1)

    if not existing:
        typer.echo("No ingest directories found.", err=True)
        typer.echo(
            "Create ~/elibrary/tmp or ~/elibrary/cart, set paths in config.yaml, "
            "or pass a path explicitly.",
            err=True,
        )
        raise typer.Exit(code=1)

    for path in missing:
        typer.echo(f"Skipping missing directory: {path}")

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

    sequence = " → ".join(str(path) for path in existing)
    typer.echo(f"Source (inbox sequence): {sequence}")
    typer.echo(f"Target (library):        {target_path}")
    typer.echo(f"Database:                {config.database_path}")
    logger.info(f"Processing PDFs from: {sequence}")

    docs = []
    for src in existing:
        found = pdf_processor.scan_directory(src)
        typer.echo(f"  {src}: {len(found)} PDF(s)")
        docs.extend(found)

    if limit is not None:
        docs = docs[:limit]
        typer.echo(f"Limit: processing first {len(docs)} PDF(s)")

    processed = []
    errors = []
    for doc in docs:
        try:
            result = file_manager.process_single_document(doc)
            if result:
                processed.append(result)
        except Exception as e:
            errors.append(f"{doc.file_path}: {e!s}")
            logger.error("process failed", path=str(doc.file_path), error=str(e))

    typer.echo(f"\nProcessed {len(processed)} documents successfully")
    logger.info(f"Processed {len(processed)} documents successfully")

    if errors:
        typer.echo(f"\nErrors ({len(errors)}):")
        logger.error(f"Errors ({len(errors)}):")
        for error in errors:
            typer.echo(f"  - {error}")
