from pathlib import Path
import subprocess
import requests
from typing import Optional, Dict

class GrobidClient:
    def __init__(self, grobid_url: str = 'http://localhost:8070'):
        self.url = grobid_url

    def process_pdf(self, pdf_path: Path) -> Optional[Dict]:
        """Send PDF to GROBID for structured extraction."""
        try:
            with open(pdf_path, 'rb') as f:
                files = {'input': f}
                response = requests.post(f'{self.url}/api/processFulltextDocument', files=files, data={'consolidateHeader': '1'})
                if response.status_code == 200:
                    return response.json() if response.headers.get('Content-Type', '').startswith('application/json') else {'xml': response.text}
            return None
        except Exception as e:
            print(f'GROBID error: {e}')
            return None
