"""
src/elib/services/pdf_processor.py
"""
import re
from pathlib import Path
from typing import Optional, List

import PyPDF2

from elib.models.document import PDFDocument, DOI

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
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) 
                                 for p in self.DOI_PATTERNS]
    
    def scan_directory(self, directory: Path) -> List[PDFDocument]:
        """Scan directory for PDF files"""
        if not directory.exists():
            raise ValueError(f"Directory does not exist: {directory}")
        
        pdf_files = list(directory.glob("**/*.pdf"))
        documents = []
        
        for pdf_path in pdf_files:
            try:
                doc = PDFDocument(
                    file_path=pdf_path,
                    original_filename=pdf_path.name,
                    file_size=pdf_path.stat().st_size
                )
                documents.append(doc)
            except Exception as e:
                print(f"Error processing {pdf_path}: {e}")
                
        return documents
    
    def extract_text(self, pdf_path: Path, max_pages: int = 3) -> str:
        """Extract text from first few pages of PDF"""
        text = ""
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                pages_to_read = min(max_pages, len(reader.pages))
                
                for i in range(pages_to_read):
                    page = reader.pages[i]
                    text += page.extract_text()
                    
        except Exception as e:
            print(f"Error extracting text from {pdf_path}: {e}")
            
        return text
    
    def find_doi(self, text: str) -> Optional[DOI]:
        """Search for DOI in text"""
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
        """Extract text and find DOI in document"""
        text = self.extract_text(document.file_path)
        document.extracted_text_preview = text[:500]
        document.doi = self.find_doi(text)
        document.processed = True
        return document
