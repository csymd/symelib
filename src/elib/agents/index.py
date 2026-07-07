def create_llama_index():
    """Create lightweight local LlamaIndex with Ollama and existing PGVector."""
    import os

    from llama_index.core import Settings, VectorStoreIndex
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from llama_index.llms.ollama import Ollama

    # NOTE: full agents support requires the [agents] extra (now includes db runtime deps)
    # + a running Postgres+pgvector DB (see compose.yml and src/elib/db/engine.py).
    # Core metadata/search remains SQLite-only.
    _ensure_settings()

    # Ollama LLM (use your installed model, e.g. llama3.1)
    # On Silverblue/Fedora Atomic + toolbox: if Ollama runs on the host ("OS root"),
    # set OLLAMA_HOST=http://host.containers.internal:11434 (or OLLAMA_BASE_URL)
    # before running elib agent / rebuild --embeddings. "ollama" command itself
    # is typically used on the host.
    ollama_base_url = os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"

    Settings.llm = Ollama(
        model="llama3.1",  # or llama3.2, phi3, etc. - change as needed
        base_url=ollama_base_url,
        request_timeout=120.0,
        temperature=0.1,  # low for factual paper work
    )

    vector_store = _get_vector_store()
    index = VectorStoreIndex.from_vector_store(vector_store)
    return index


def _ensure_settings():
    """Set the shared embedding model (used by both query and population paths)."""
    from llama_index.core import Settings
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    Settings.embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")


def _get_vector_store():
    """Create (or return configured) PGVectorStore. Assumes DB is up."""
    from llama_index.vector_stores.postgres import PGVectorStore
    from sqlalchemy import make_url, text

    from elib.db.engine import get_engine

    engine = get_engine()
    url = make_url(str(engine.url))

    # Best-effort: ensure the vector extension exists.
    # The preferred way is now `make db-migrate` (see 0001_initial_vector_store).
    # This remains as a fallback for setups that haven't run the migration yet.
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()
    except Exception:
        # If it fails (already exists, or permissions), the vector store operations will surface a clearer error.
        pass

    vector_store = PGVectorStore.from_params(
        database=url.database,
        host=url.host,
        password=url.password,
        port=url.port,
        user=url.username,
        table_name="document_nodes",
        embed_dim=384,  # matches all-MiniLM-L6-v2
        # perform_setup left at default (True) so the vector store can still
        # create the table as a fallback if `make db-migrate` was not run.
        # The migration (0001) is the recommended/official way.
    )
    return vector_store


def populate_embeddings(db_manager, max_pages_per_pdf: int | None = 40, reset: bool = False):
    """
    Populate (or update) the PGVector store using documents in the SQLite DB.

    - Prefers real text extracted from the stored PDF files (via PDFProcessor).
    - Falls back to title+abstract+metadata when the PDF file is missing.
    - Uses LlamaIndex SentenceSplitter for sensible chunking (good for scientific papers).
    - Attaches rich metadata (doi, title, file_path, etc.) to every chunk.
    - Uses stable node IDs (doi::chunk-XXXX).

    By default this does a "smart update": it removes previous chunks for each paper's DOI
    before inserting the new ones. This makes repeated runs safe and keeps the index fresh
    without massive duplication.

    If reset=True, it clears the entire vector store first.

    Run this after `elib process ...` (core) and `make db-up`.

    Returns the number of *source documents* that were processed (not the final chunk count).
    """
    from pathlib import Path

    from llama_index.core import Document, StorageContext, VectorStoreIndex
    from llama_index.core.node_parser import SentenceSplitter

    from elib.services.pdf_processor import PDFProcessor

    _ensure_settings()
    vector_store = _get_vector_store()

    metas = db_manager.list_documents()
    if not metas:
        print("No documents found in the local SQLite DB.")
        print("Run 'elib process <dir>' (core path) first to ingest some papers.")
        return 0

    if reset:
        clear_embeddings()

    # Smart update: remove any previous chunks for the papers we are (re)indexing.
    # This prevents unbounded duplication when you run --embeddings multiple times
    # or after adding more papers.
    if not reset:
        unique_dois = {m.doi for m in metas if getattr(m, "doi", None)}
        cleared = 0
        for doi in unique_dois:
            try:
                vector_store.delete(ref_doc_id=doi)
                cleared += 1
            except Exception:
                # Table may not exist yet, or no previous nodes for this DOI — that's fine.
                pass
        if cleared:
            print(f"Cleared previous chunks for {cleared} paper(s) before re-embedding.")

    pdf_processor = PDFProcessor()
    splitter = SentenceSplitter(chunk_size=450, chunk_overlap=60)

    source_docs = 0
    all_nodes = []

    for m in metas:
        text = ""
        pdf_path = Path(m.file_path) if m.file_path else None

        if pdf_path and pdf_path.exists():
            try:
                text = pdf_processor.extract_full_text(pdf_path, max_pages=max_pages_per_pdf)
            except Exception as e:
                print(f"  Warning: full-text extract failed for {pdf_path.name}: {e}")
                text = ""

        if not text or len(text) < 50:
            # Fallback to whatever metadata we have
            parts = [m.title]
            if m.abstract:
                parts.append(m.abstract)
            if m.journal:
                parts.append(f"Journal: {m.journal}")
            if m.publication_year:
                parts.append(f"Year: {m.publication_year}")
            if m.authors_json and m.authors_json not in ("[]", "null", ""):
                parts.append(f"Authors: {m.authors_json}")
            text = " | ".join(parts)

        if not text.strip():
            continue

        base_meta = {
            "title": m.title,
            "doi": m.doi,
            "pmid": m.pmid,
            "journal": m.journal,
            "year": m.publication_year,
            "file_path": str(m.file_path) if m.file_path else None,
            "source": "elib-pdf",
        }

        doc = Document(text=text, metadata=base_meta)
        if m.doi:
            doc.doc_id = m.doi

        nodes = splitter.get_nodes_from_documents([doc])

        for i, node in enumerate(nodes):
            doi_part = (m.doi or "unknown").replace("/", "_")
            node.id_ = f"{doi_part}::chunk-{i:04d}"
            node.metadata.update(base_meta)
            node.metadata["chunk_index"] = i
            node.metadata["num_chunks_for_doc"] = len(nodes)

        all_nodes.extend(nodes)
        source_docs += 1

        if len(nodes) > 0:
            print(f"  {m.title[:55]}... -> {len(nodes)} chunks")

    if all_nodes:
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        VectorStoreIndex(
            nodes=all_nodes,
            storage_context=storage_context,
        )
        print(f"\nEmbedded and stored {len(all_nodes)} chunks from {source_docs} papers into PGVector.")
    else:
        print("No usable text found to embed.")

    return source_docs


def clear_embeddings():
    """Remove all nodes from the vector store (nuclear reset)."""
    from sqlalchemy import text

    from elib.db.engine import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM data_document_nodes"))
        conn.commit()
    print("Cleared all vector embeddings from the Postgres store.")


def get_node_count() -> int:
    """Return how many nodes are currently stored in the vector index (best effort)."""
    from sqlalchemy import text

    from elib.db.engine import get_engine

    try:
        engine = get_engine()
        with engine.connect() as conn:
            res = conn.execute(text("SELECT COUNT(*) FROM data_document_nodes"))
            return int(res.scalar() or 0)
    except Exception:
        return 0


def get_query_engine():
    """Simple RAG query engine for papers."""
    index = create_llama_index()
    return index.as_query_engine(similarity_top_k=5)


# Backwards/compat note: older code may have expected a different entry point.
# The main public functions are create_llama_index, get_query_engine, and populate_embeddings.
