"""initial pgvector setup for document_nodes

Revision ID: 0001_initial_vector_store
Revises: 
Create Date: 2026-06-09

This is the first migration for the optional Postgres + pgvector vector store
used by the agents/RAG path (via llama-index-vector-stores-postgres).

It enables the vector extension and creates the table that LlamaIndex's
PGVectorStore (with table_name="document_nodes", embed_dim=384, non-hybrid)
will use: `data_document_nodes`.

Note:
- The main application still uses SQLite for document metadata/FTS.
- This migration only affects the agents vector store path.
- LlamaIndex's PGVectorStore (perform_setup=True) will also attempt to
  create the table, but having it in Alembic gives us proper version control
  and makes `make db-migrate` meaningful.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, VARCHAR


# revision identifiers, used by Alembic.
revision = "0001_initial_vector_store"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable the pgvector extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Create the table matching LlamaIndex PGVectorStore.get_data_model
    # for non-hybrid search, table_name="document_nodes" -> actual "data_document_nodes",
    # embed_dim=384, use_jsonb=False (so JSON not JSONB), no halfvec.
    #
    # Columns from the dynamic model in llama_index/vector_stores/postgres/base.py:
    #   id BIGINT PK autoincrement
    #   text VARCHAR NOT NULL
    #   metadata_ JSON
    #   node_id VARCHAR
    #   embedding vector(384)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS data_document_nodes (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            text VARCHAR NOT NULL,
            metadata_ JSON,
            node_id VARCHAR,
            embedding vector(384)
        )
        """
    )

    # Create the index on ref_doc_id that LlamaIndex creates for lookups
    # (used when we set doc.doc_id which becomes metadata_['ref_doc_id'])
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS document_nodes_idx_1
        ON data_document_nodes USING btree ( (metadata_->>'ref_doc_id') )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS document_nodes_idx_1;")
    op.execute("DROP TABLE IF EXISTS data_document_nodes;")
    # We generally do not drop the extension on downgrade, as it may be used by other things.
    # op.execute("DROP EXTENSION IF EXISTS vector;")
