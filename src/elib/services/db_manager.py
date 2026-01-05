"""
elib/services/db_manager.py
"""
import json
import sqlite3

from pathlib import Path
from typing import List, Optional
from contextlib import contextmanager

from ..models.metadata import DocumentMetadata, SearchQuery, SearchResult
from ..models.reference import Reference

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
        """Search documents based on query parameters"""
        sql_parts = ['SELECT * FROM documents WHERE 1=1']
        params = []
        
        if query.text:
            sql_parts.append('''
                AND id IN (
                    SELECT rowid FROM documents_fts 
                    WHERE documents_fts MATCH ?
                )
            ''')
            params.append(query.text)
        
        if query.author:
            sql_parts.append('AND authors_json LIKE ?')
            params.append(f'%{query.author}%')
        
        if query.year_from:
            sql_parts.append('AND publication_year >= ?')
            params.append(query.year_from)
        
        if query.year_to:
            sql_parts.append('AND publication_year <= ?')
            params.append(query.year_to)
        
        if query.keywords:
            for keyword in query.keywords:
                sql_parts.append('AND keywords_json LIKE ?')
                params.append(f'%{keyword}%')
        
        sql_parts.append(f'LIMIT ? OFFSET ?')
        params.extend([query.limit, query.offset])
        
        sql = ' '.join(sql_parts)
        
        results = []
        with self.get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            for row in rows:
                metadata = DocumentMetadata(**dict(row))
                results.append(SearchResult(
                    metadata=metadata,
                    relevance_score=1.0
                ))
        
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
