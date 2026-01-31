

        
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
