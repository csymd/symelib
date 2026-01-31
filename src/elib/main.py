"""
src/elib/main.py

The entry point for the elib CLI application.
"""
from __future__ import annotations

import typer
from typing import Optional

from elib.cli.stats import stats
from elib.cli.search import search
from elib.cli.process import process
from elib.cli.rebuild_index import rebuild_index

from elib.utils.logging import initialize_logger, LogLevel

# ========================================================= #
# elib CLI Application                                      #
# ========================================================= #

app = typer.Typer(help="elib - Electronic Library Management System")
app.command(name='stats')(stats)
app.command(name='search')(search)
app.command(name='process')(process)
app.command(name='rebuild-index')(rebuild_index)


# ========================================================= #
# Global CLI Options                                        #
# ========================================================= #
# 
@app.callback()
def main(
    ctx: typer.Context,
    verbose: int = typer.Option(0, "--verbose", "-v", help="Increase verbosity"),
    quiet: bool = typer.Option(True, "--quiet", "-q", help="Quiet mode"),
    log_level: Optional[LogLevel] = typer.Option(None, "--log-level", help="Set log level"),
):
    """
    Global CLI options (verbosity, quiet, log level).
    """
    # Default log level
    log_level = log_level or LogLevel.INFO

    # Initialize logger + config
    config, logger = initialize_logger(verbose=verbose, quiet=quiet, log_level=log_level)

    # Attach to context so subcommands can use it
    ctx.obj = {"config": config, "logger": logger}


def runner():
    """
    Entrypoint for pyproject.toml
    """
    app()


if __name__ == "__main__":
    runner()
