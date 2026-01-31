"""
src/elib/main.py

The entry point for the elib CLI application.
"""
import typer
from elib.utils.logging import initialize_logger
from elib.cli.process import app as process_app
from elib.cli.search import app as search_app
from elib.cli.stats import app as stats_app
from elib.cli.rebuild_index import app as rebuild_index_app

app = typer.Typer(help='elib - Electronic Library Management System')

# Add subcommands
app.add_typer(process_app, name='process')
app.add_typer(search_app, name='search')
app.add_typer(stats_app, name='stats')
app.add_typer(rebuild_index_app, name='rebuild-index')

@app.callback()
def main(
        verbose: int = typer.Option(0, '--verbose', '-v', help='Increase verbosity'),
        quiet: bool = typer.Option(False, '--quiet', '-q', help='Quiet mode'),
        log_level: str = typer.Option(None, '--log-level', help='Set log level',
                                    case_sensitive=False,
                                    show_choices=True,
                                    choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']),
    ):
    """
    Main entry point for the CLI application.
    """
    config, logger = initialize_logger(verbose, quiet, log_level)
    typer.Context.obj = {'config': config, 'logger': logger}

    
if __name__ == '__main__':
    app()
