from rich.console import Console
import typer

app = typer.Typer()
console = Console()


@app.command()
def agent(query: str):
    """Run a lightweight local agent query over your papers."""
    try:
        from symworx_elibrary.agents.index import get_query_engine
    except ImportError as e:
        console.print("[red]Agent features require the 'agents' extra.[/red]")
        console.print("Run: uv sync --extra agents   (or uv sync --all-extras)")
        console.print("Also ensure: make db-up  (Postgres + pgvector) and Ollama is running.")
        console.print(f"Details: {e}")
        raise typer.Exit(1) from e

    console.print(f"[bold]Querying papers:[/bold] {query}")
    try:
        # Give the user visibility into how much data the RAG index actually has
        try:
            from symworx_elibrary.agents.index import get_node_count

            node_count = get_node_count()
            if node_count == 0:
                console.print("[yellow]Note:[/yellow] The vector index currently has 0 chunks.")
                console.print(
                    "       Run `elib rebuild-index --embeddings` after processing some PDFs."
                )
            else:
                console.print(f"[dim]Searching across ~{node_count} indexed chunks...[/dim]")
        except Exception:
            pass  # non-fatal if we can't get the count

        query_engine = get_query_engine()
        response = query_engine.query(query)
        console.print(response)
        return response
    except Exception as e:
        console.print(f"[red]Agent query failed:[/red] {e}")
        console.print(
            "Ensure 'agents' extra is installed, Ollama is running, and the DB is up (make db-up)."
        )
        console.print(
            "You may also need to run `elib rebuild-index --embeddings` after ingesting papers."
        )
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
