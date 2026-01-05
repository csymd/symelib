"""
elib/services/db_manager.py
"""
import json
import sqlite3

from pathlib import Path
from typing import List, Optional
from contextlib import contextmanager

from elib.models.metadata import (
    DocumentMetadata,
    SearchQuery,
    SearchResult,
    SortBy,
    SortOrder,
)
from elib.models.reference import Reference
from elib.utils.logging import get_shared_logger

logger = get_shared_logger(name="db_manager")

# ========================================================= #
# Database Manager Service                                  #
# ========================================================= #

class DatabaseManager:
    """Manages the SQLite database for document metadata"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database and create tables if they don't exist"""
        with self.get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    doi TEXT NOT NULL,
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
                    s3_path TEXT
                )
            ''')
            
            # Create indexes
            conn.execute('CREATE INDEX IF NOT EXISTS idx_doi ON documents(doi)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_pmid ON documents(pmid)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_year ON documents(publication_year)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_filename ON documents(filename)')
            
            # Full-text search virtual table
            conn.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                    title, authors_json, abstract, keywords_json,
                    content=documents,
                    content_rowid=id
                )
            ''')
            
            # Triggers to keep FTS in sync
            conn.execute('''
                CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                    INSERT INTO documents_fts(rowid, title, authors_json, abstract, keywords_json)
                    VALUES (new.id, new.title, new.authors_json, new.abstract, new.keywords_json);
                END
            ''')
            
            conn.execute('''
                CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                    DELETE FROM documents_fts WHERE rowid = old.id;
                END
            ''')
            
            conn.execute('''
                CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                    UPDATE documents_fts SET 
                        title = new.title,
                        authors_json = new.authors_json,
                        abstract = new.abstract,
                        keywords_json = new.keywords_json
                    WHERE rowid = new.id;
                END
            ''')
            
            conn.commit()
    
    @contextmanager
    def get_connection(self):
        '''Context manager for database connections'''
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def add_document(self, reference: Reference, file_path: Path, 
                     filename: str, file_size: int) -> int:
        '''Add document to database'''
        authors_json = json.dumps([a.dict() for a in reference.authors])
        keywords_json = json.dumps(reference.keywords + reference.mesh_terms)
        
        metadata = DocumentMetadata(
            file_path=str(file_path),
            filename=filename,
            doi=reference.doi,
            pmid=reference.pmid,
            title=reference.title,
            authors_json=authors_json,
            journal=reference.journal.title,
            publication_year=reference.publication_date.year if reference.publication_date else None,
            abstract=reference.abstract,
            keywords_json=keywords_json,
            file_size=file_size
        )
        
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO documents (
                    file_path, filename, doi, pmid, title, authors_json,
                    journal, publication_year, abstract, keywords_json, file_size
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                metadata.file_path, metadata.filename, metadata.doi,
                metadata.pmid, metadata.title, metadata.authors_json,
                metadata.journal, metadata.publication_year, metadata.abstract,
                metadata.keywords_json, metadata.file_size
            ))
            conn.commit()
            return cursor.lastrowid
    
    def get_by_doi(self, doi: str) -> Optional[DocumentMetadata]:
        """Get document metadata by DOI"""
        with self.get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM documents WHERE doi = ?', (doi,)
            ).fetchone()
            
            if row:
                return DocumentMetadata(**dict(row))
        return None
    
    def search(self, query: SearchQuery) -> List[SearchResult]:
        """Search documents with filters and FTS ranking."""

        params = []

        if query.text:
            # Check if user wants boolean search (contains AND/OR/NOT)
            has_boolean = any(op in query.text.upper() for op in [' AND ', ' OR ', ' NOT '])

            if has_boolean:
                # User wants boolean search - pass as-is
                fts_query = query.text
                logger.debug('Boolean FTS query', query=fts_query)
            else:
                # Normal search - escape and wrap in quotes
                escaped_text = query.text.replace('"', '""')
                fts_query = f'"{escaped_text}"'
                logger.debug('Phrase FTS query', query=fts_query)

            sql = '''
                SELECT d.*,
                    bm25(documents_fts) AS relevance
                FROM documents d
                JOIN documents_fts ON documents_fts.rowid = d.id
                WHERE documents_fts MATCH ?
            '''
            params.append(fts_query)

            logger.debug('FTS query prepared', 
                        original=query.text,
                        escaped=fts_query)
        else:
            # No text search - just filter on metadata
            sql = '''
                SELECT d.*,
                    0.0 AS relevance
                FROM documents d
                WHERE 1=1
            '''

        # Author filter
        if query.author:
            sql += ' AND d.authors_json LIKE ?'
            params.append(f'%{query.author}%')

        # Year range filters
        if query.year_from:
            sql += ' AND d.publication_year >= ?'
            params.append(query.year_from)

        if query.year_to:
            sql += ' AND d.publication_year <= ?'
            params.append(query.year_to)

        # Journal filter
        if query.journal:
            sql += ' AND d.journal LIKE ?'
            params.append(f'%{query.journal}%')

        # DOI exact match
        if query.doi:
            sql += ' AND d.doi = ?'
            params.append(query.doi)

        # PMID exact match
        if query.pmid:
            sql += ' AND d.pmid = ?'
            params.append(query.pmid)

        # Keyword filters (all must match)
        for kw in query.keywords:
            sql += ' AND d.keywords_json LIKE ?'
            params.append(f'%{kw}%')

        # Sorting
        if query.sort_by == SortBy.relevance and query.text:
            # Sort by FTS relevance (lower bm25 score = more relevant)
            sql += ' ORDER BY relevance ASC'
        elif query.sort_by == SortBy.year:
            order = 'ASC' if query.sort_order == SortOrder.asc else 'DESC'
            sql += f' ORDER BY d.publication_year {order}'
        elif query.sort_by == SortBy.title:
            order = 'ASC' if query.sort_order == SortOrder.asc else 'DESC'
            sql += f' ORDER BY d.title {order}'
        else:  # added_date
            order = 'ASC' if query.sort_order == SortOrder.asc else 'DESC'
            sql += f' ORDER BY d.added_date {order}'

        # Pagination
        sql += ' LIMIT ? OFFSET ?'
        params.extend([query.limit, query.offset])

        logger.debug('Executing search query',
                    sql_preview=sql[:300],
                    param_count=len(params))

        # Execute query and build results
        results = []
        try:
            with self.get_connection() as conn:
                rows = conn.execute(sql, params).fetchall()

                for row in rows:
                    meta = DocumentMetadata(**dict(row))
                    # Note: BM25 returns negative scores (lower = more relevant)
                    # Convert to positive for display
                    relevance = abs(row['relevance']) if row['relevance'] else 0.0
                    results.append(SearchResult(
                        metadata=meta,
                        relevance_score=relevance
                    ))

            logger.info('Search completed successfully',
                    result_count=len(results),
                    query_text=query.text)

        except Exception as e:
            logger.error('Search query failed',
                        error=str(e),
                        error_type=type(e).__name__,
                        sql_preview=sql[:200])
            raise

        return results
    
    def update_s3_sync(self, doc_id: int, s3_path: str):
        """Update document record as synced to S3"""
        with self.get_connection() as conn:
            conn.execute('''
                UPDATE documents 
                SET s3_synced = 1, s3_path = ?
                WHERE id = ?
            ''', (s3_path, doc_id))
            conn.commit()

    def rebuild_fts_index(self):
        """Rebuild full-text search index from existing documents."""
        logger.info("Rebuilding FTS index")

        with self.get_connection() as conn:
            # Clear existing FTS data
            conn.execute("DELETE FROM documents_fts")

            # Repopulate from documents table
            conn.execute("""
                INSERT INTO documents_fts(rowid, title, authors_json, abstract, keywords_json)
                SELECT id, title, authors_json, abstract, keywords_json
                FROM documents
            """)

            count = conn.execute("SELECT COUNT(*) FROM documents_fts").fetchone()[0]
            conn.commit()

        logger.info("FTS index rebuilt", document_count=count)
        return count
