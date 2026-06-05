import typer
from rich.console import Console
from elib.agents.index import get_query_engine

app = typer.Typer()
console = Console()

@app.command()
def agent(query: str):
    """Run a lightweight local agent query over your papers."""
    console.print(f"[bold]Querying papers:[/bold] {query}")
    query_engine = get_query_engine()
    response = query_engine.query(query)
    console.print(response)
    return response

if __name__ == "__main__":
    app()