"""
src/elib/services/pdf_processor.py
"""
import re
from pathlib import Path
from typing import Optional, List

import PyPDF2

from elib.models.document import PDFDocument, DOI
from elib.utils.logging import get_shared_logger

logger = get_shared_logger(name='pdf_processor')

# ========================================================= #
# PDF Processing Service                                    #
# ========================================================= #

class PDFProcessor:
    """Service for processing PDF files"""
    
    DOI_PATTERNS = [
        r'10\.\d{4,}/[-._;()\/:A-Za-z0-9]+',
        r'doi:\s*10\.\d{4,}/[-._;()\/:A-Za-z0-9]+',
        r'DOI:\s*10\.\d{4,}/[-._;()\/:A-Za-z0-9]+',
    ]
    
    def __init__(self):
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.DOI_PATTERNS]
        logger.info('PDFProcessor initialized', pattern_count=len(self.compiled_patterns))
    
    def scan_directory(self, directory: Path) -> List[PDFDocument]:
        """Scan directory for PDF files"""
        logger.info('Starting directory scan', directory=str(directory))
        if not directory.exists():
            logger.error('Directory does not exist', directory=str(directory))
            raise ValueError(f'Directory does not exist: {directory}')
        
        pdf_files = list(directory.glob('**/*.pdf'))
        logger.info('PDF files discovered',
                    file_count=len(pdf_files),
                    directory=str(directory),) 

        documents = []
        
        for pdf_path in pdf_files:
            try:
                doc = PDFDocument(
                    file_path=pdf_path,
                    original_filename=pdf_path.name,
                    file_size=pdf_path.stat().st_size
                )
                documents.append(doc)
                logger.debug('PDF document added', file_path=str(pdf_path))
            except Exception as e:
                logger.error('Error processing PDF file', file_path=str(pdf_path), error=str(e))
                print(f'Error processing {pdf_path}: {e}')
                
        return documents
    
    def extract_text(self, pdf_path: Path, max_pages: int = 3) -> str:
        """Extract text from the first few pages of a PDF"""
        text = ''
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                pages_to_read = min(max_pages, len(reader.pages))
                
                for i in range(pages_to_read):
                    page = reader.pages[i]
                    text += page.extract_text()
                    
        except Exception as e:
            print(f'Error extracting text from {pdf_path}: {e}')
            
        return text
    
    def find_doi(self, text: str) -> Optional[DOI]:
        """Find DOI in extracted text"""
        for pattern in self.compiled_patterns:
            match = pattern.search(text)
            if match:
                doi_string = match.group(0)
                # Clean up the DOI
                doi_string = doi_string.replace('doi:', '').replace('DOI:', '').strip()
                try:
                    return DOI(value=doi_string)
                except ValueError:
                    continue
        return None
    
    def process_document(self, document: PDFDocument) -> PDFDocument:
        """Process a single PDF document to extract text and find DOI"""
        text = self.extract_text(document.file_path)
        document.extracted_text_preview = text[:500]
        document.doi = self.find_doi(text)
        document.processed = True
        return document
