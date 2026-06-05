from llama_index.core import VectorStoreIndex, Settings
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import os
from sqlalchemy import make_url

from elib.db.engine import get_engine


def create_llama_index():
    """Create lightweight local LlamaIndex with Ollama and existing PGVector."""
    # Use existing embeddings model for consistency
    Settings.embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")
    
    # Ollama LLM (use your installed model, e.g. llama3.1)
    Settings.llm = Ollama(
        model="llama3.1",  # or llama3.2, phi3, etc. - change as needed
        request_timeout=120.0,
        temperature=0.1,  # low for factual paper work
    )
    
    # Connect to existing Postgres + pgvector
    engine = get_engine()
    url = make_url(str(engine.url))
    
    vector_store = PGVectorStore.from_params(
        database=url.database,
        host=url.host,
        password=url.password,
        port=url.port,
        user=url.username,
        table_name="document_nodes",  # or link to your documents
        embed_dim=384,  # matches all-MiniLM-L6-v2
    )
    
    index = VectorStoreIndex.from_vector_store(vector_store)
    return index


def get_query_engine():
    """Simple RAG query engine for papers."""
    index = create_llama_index()
    return index.as_query_engine(similarity_top_k=5)