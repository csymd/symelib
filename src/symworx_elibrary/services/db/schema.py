"""
SQLite persistence for elib (split package).
"""

from __future__ import annotations

from contextlib import contextmanager
import sqlite3

from symworx_elibrary.models.metadata import (
    MetadataSource,
    classify_metadata_status,
    has_real_doi,
    is_synthetic_doi,
    is_synthetic_pmid,
)
from symworx_elibrary.services.db.base import _DOCUMENTS_EXTRA_COLUMNS
from symworx_elibrary.utils.logging import LoggerConfig, get_shared_logger

logger = get_shared_logger(LoggerConfig(name="db_manager"))


class SchemaMixin:
    """Schema init, migrations, FTS, backfill."""

    def init_database(self):
        """Initialize database and create tables if they don't exist"""
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    doi TEXT NOT NULL DEFAULT '',
                    pmid TEXT,
                    title TEXT NOT NULL,
                    authors_json TEXT NOT NULL,
                    journal TEXT NOT NULL,
                    publication_year INTEGER,
                    abstract TEXT,
                    keywords_json TEXT DEFAULT '[]',
                    file_size INTEGER NOT NULL,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP,
                    s3_synced BOOLEAN DEFAULT 0,
                    s3_path TEXT,
                    metadata_status TEXT NOT NULL DEFAULT 'pending',
                    metadata_source TEXT,
                    metadata_checked_at TIMESTAMP
                )
            """)

            self._migrate_documents_schema(conn)

            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_doi ON documents(doi)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pmid ON documents(pmid)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_year ON documents(publication_year)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_filename ON documents(filename)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_metadata_status ON documents(metadata_status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_metadata_issue ON documents(metadata_issue)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_source_path ON documents(source_path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_added_date ON documents(added_date)")
            # Unique DOI only when a real (non-empty) value is present.
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_doi_unique
                ON documents(doi)
                WHERE doi IS NOT NULL AND doi != ''
            """)

            # Standalone FTS5 index (not content=) so UPDATE/DELETE stay simple and reliable.
            # Search always JOINs back to documents for full rows.
            self._ensure_fts_table(conn)

            # Named paper lists (grants / manuscripts)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_lists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP
                )
            """)
            # Soft-delete column for existing DBs
            pl_cols = {row[1] for row in conn.execute("PRAGMA table_info(paper_lists)").fetchall()}
            if "deleted_at" not in pl_cols:
                conn.execute("ALTER TABLE paper_lists ADD COLUMN deleted_at TIMESTAMP")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_list_items (
                    list_id INTEGER NOT NULL REFERENCES paper_lists(id) ON DELETE CASCADE,
                    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    notes TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (list_id, document_id)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_list_items_doc ON paper_list_items(document_id)"
            )

            conn.commit()

        # If documents exist but FTS is empty/out of sync (e.g. legacy DB just gained FTS), rebuild.
        self._ensure_fts_synced()

        # Backfill status/source for rows that predate these columns or still say pending.
        self.backfill_metadata_status()

    def _migrate_documents_schema(self, conn: sqlite3.Connection) -> None:
        """Add new columns on existing databases (SQLite ALTER TABLE)."""
        existing = {row[1] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
        for col_name, col_def in _DOCUMENTS_EXTRA_COLUMNS:
            if col_name not in existing:
                logger.info("Migrating documents schema: adding column", column=col_name)
                conn.execute(f"ALTER TABLE documents ADD COLUMN {col_name} {col_def}")

    def _ensure_fts_table(self, conn: sqlite3.Connection) -> None:
        """
        Ensure a standalone (non content=) documents_fts table and sync triggers exist.

        Older elib versions used content=documents FTS5, whose AFTER UPDATE triggers can
        mark the DB malformed when content and index diverge. We migrate by rebuilding
        a standalone FTS table when the content= option is detected.
        """
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='documents_fts'"
        ).fetchone()
        needs_recreate = False
        if row is None:
            needs_recreate = True
        else:
            sql = (row[0] or "").lower()
            if "content=" in sql or "content='" in sql or 'content="' in sql:
                logger.info("Migrating FTS: replacing content= documents_fts with standalone index")
                needs_recreate = True

        if needs_recreate:
            conn.execute("DROP TRIGGER IF EXISTS documents_ai")
            conn.execute("DROP TRIGGER IF EXISTS documents_ad")
            conn.execute("DROP TRIGGER IF EXISTS documents_au")
            conn.execute("DROP TRIGGER IF EXISTS documents_bu")
            conn.execute("DROP TRIGGER IF EXISTS documents_bd")
            # Drop old FTS (and its shadow tables)
            conn.execute("DROP TABLE IF EXISTS documents_fts")
            conn.execute("""
                CREATE VIRTUAL TABLE documents_fts USING fts5(
                    title, authors_json, abstract, keywords_json
                )
            """)
        else:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                    title, authors_json, abstract, keywords_json
                )
            """)

        # Always refresh triggers to the standalone-safe form
        conn.execute("DROP TRIGGER IF EXISTS documents_ai")
        conn.execute("DROP TRIGGER IF EXISTS documents_ad")
        conn.execute("DROP TRIGGER IF EXISTS documents_au")
        conn.execute("DROP TRIGGER IF EXISTS documents_bu")
        conn.execute("DROP TRIGGER IF EXISTS documents_bd")

        conn.execute("""
            CREATE TRIGGER documents_ai AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, title, authors_json, abstract, keywords_json)
                VALUES (new.id, new.title, new.authors_json, new.abstract, new.keywords_json);
            END
        """)
        conn.execute("""
            CREATE TRIGGER documents_ad AFTER DELETE ON documents BEGIN
                DELETE FROM documents_fts WHERE rowid = old.id;
            END
        """)
        conn.execute("""
            CREATE TRIGGER documents_au AFTER UPDATE ON documents BEGIN
                DELETE FROM documents_fts WHERE rowid = old.id;
                INSERT INTO documents_fts(rowid, title, authors_json, abstract, keywords_json)
                VALUES (new.id, new.title, new.authors_json, new.abstract, new.keywords_json);
            END
        """)

    def backfill_metadata_status(self, force: bool = False) -> int:
        """
        Infer metadata_status / metadata_source for rows that need it.

        By default only updates rows with status 'pending' or NULL.
        Returns the number of rows updated.
        """
        updated = 0
        with self.get_connection() as conn:
            if force:
                rows = conn.execute("SELECT * FROM documents").fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM documents
                    WHERE metadata_status IS NULL
                       OR metadata_status = ''
                       OR metadata_status = 'pending'
                    """
                ).fetchall()

            for row in rows:
                data = dict(row)
                doi = data.get("doi") or ""
                pmid = data.get("pmid")
                status = classify_metadata_status(
                    doi=doi,
                    pmid=pmid,
                    title=data.get("title"),
                    authors_json=data.get("authors_json"),
                    abstract=data.get("abstract"),
                )

                # Infer source from identifiers / synthetic markers
                if is_synthetic_doi(doi) and is_synthetic_pmid(pmid):
                    source = MetadataSource.local.value
                elif has_real_doi(doi) or (pmid and not is_synthetic_pmid(pmid)):
                    # Historical rows came from PubMed; refine later via enrich
                    source = MetadataSource.pubmed.value
                else:
                    source = MetadataSource.local.value

                # Normalize synthetic DOI to empty string so unique index stays clean
                new_doi = "" if is_synthetic_doi(doi) else doi
                new_pmid = None if is_synthetic_pmid(pmid) else pmid

                conn.execute(
                    """
                    UPDATE documents
                    SET metadata_status = ?,
                        metadata_source = COALESCE(metadata_source, ?),
                        doi = ?,
                        pmid = ?
                    WHERE id = ?
                    """,
                    (status.value, source, new_doi, new_pmid, data["id"]),
                )
                updated += 1

            conn.commit()

        if updated:
            logger.info("Backfilled metadata status", rows_updated=updated)
        return updated

    @contextmanager
    def _ensure_fts_synced(self) -> None:
        """Rebuild FTS when document count and FTS row count diverge."""
        try:
            docs = self.count_documents()
            fts = self.count_fts()
        except sqlite3.Error:
            return
        if docs != fts:
            logger.info(
                "FTS out of sync with documents; rebuilding",
                documents=docs,
                fts=fts,
            )
            self.rebuild_fts_index()

    def update_s3_sync(self, doc_id: int, s3_path: str):
        """Update document record as synced to S3"""
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE documents
                SET s3_synced = 1, s3_path = ?
                WHERE id = ?
            """,
                (s3_path, doc_id),
            )
            conn.commit()

    def rebuild_fts_index(self):
        """Rebuild full-text search index from existing documents."""
        logger.info("Rebuilding FTS index")

        with self.get_connection() as conn:
            conn.execute("DELETE FROM documents_fts")
            conn.execute("""
                INSERT INTO documents_fts(rowid, title, authors_json, abstract, keywords_json)
                SELECT id, title, authors_json, abstract, keywords_json
                FROM documents
            """)
            count = conn.execute("SELECT COUNT(*) FROM documents_fts").fetchone()[0]
            conn.commit()

        logger.info("FTS index rebuilt", document_count=count)
        return count
