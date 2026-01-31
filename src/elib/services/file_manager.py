"""
src/elib/services/file_manager.py
"""
import shutil
from pathlib import Path
from typing import List, Tuple, Optional

from elib.utils.logging import LoggerConfig, get_shared_logger
from elib.models.document import PDFDocument, ProcessedDocument
# from elib.models.reference import Reference
from elib.services.db_manager import DatabaseManager
from elib.services.ncbi_client import NCBIClient
from elib.services.pdf_processor import PDFProcessor

# === Initialize Logger ===
logger = get_shared_logger(LoggerConfig(name="db_manager"))

# ========================================================= #
# File Manager Service                                      #
# ========================================================= #

class FileManager:
    """Service for managing PDF files and metadata"""
    
    def __init__(self, 
                 pdf_processor: PDFProcessor,
                 ncbi_client: NCBIClient,
                 db_manager: DatabaseManager,
                 target_directory: Path):
        self.pdf_processor = pdf_processor
        self.ncbi_client = ncbi_client
        self.db_manager = db_manager
        self.target_directory = target_directory
        self.target_directory.mkdir(parents=True, exist_ok=True)
    
    def process_directory(self, source_dir: Path) -> Tuple[List[ProcessedDocument], List[str]]:
        """Process all PDF documents in the source directory"""
        documents = self.pdf_processor.scan_directory(source_dir)
        processed = []
        errors = []
        
        for doc in documents:
            try:
                result = self.process_single_document(doc)
                if result:
                    processed.append(result)
            except Exception as e:
                errors.append(f'{doc.file_path}: {str(e)}')
        
        return processed, errors
    
    def process_single_document(self, document: PDFDocument) -> Optional[ProcessedDocument]:
        """Process a single PDF document"""
        print(f'Processing: {document.file_path}')
        
        # Extract text and find DOI
        document = self.pdf_processor.process_document(document)
        
        if not document.doi:
            print(f'  No DOI found in {document.file_path}')
            return None
        
        print(f'  Found DOI: {document.doi}')
        
        # Check if already in database
        existing = self.db_manager.get_by_doi(document.doi.value)
        if existing:
            print(f'  Already in database: {existing.filename}')
            return None
        
        # Search NCBI
        pmid = self.ncbi_client.search_by_doi(document.doi.value)
        if not pmid:
            print(f'  No PMID found for DOI: {document.doi}')
            return None
        
        print(f'  Found PMID: {pmid}')
        
        # Fetch full reference
        reference = self.ncbi_client.fetch_reference(pmid)
        if not reference:
            print(f'  Could not fetch reference for PMID: {pmid}')
            return None
        
        print(f'  Title: {reference.title[:60]}...')
        
        # Generate new filename
        new_filename = reference.generate_filename()
        new_path = self.target_directory / new_filename
        
        # Handle filename conflicts
        counter = 1
        while new_path.exists():
            stem = new_path.stem
            new_path = self.target_directory / f'{stem}_{counter}.pdf'
            counter += 1
        
        # Copy/move file
        shutil.copy2(document.file_path, new_path)
        print(f'  Copied to: {new_path}')
        
        # Add to database
        doc_id = self.db_manager.add_document(
            reference=reference,
            file_path=new_path,
            filename=new_path.name,
            file_size=document.file_size
        )
        print(f'  Added to database with ID: {doc_id}')
        
        return ProcessedDocument(
            file_path=new_path,
            original_filename=document.original_filename,
            file_size=document.file_size,
            doi=document.doi,
            new_filename=new_path.name,
            pmid=pmid,
            metadata_stored=True
        )
