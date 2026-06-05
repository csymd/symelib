"""
NCBI E-utilities client with HTTP and CLI backend support.
"""
from abc import ABC, abstractmethod
from datetime import datetime
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import requests

from elib.models.reference import Author, Journal, Reference
from elib.services.search_pubmed import PubMedSearchService
from elib.utils.logging import LoggerConfig, get_shared_logger
from elib.utils.rate_limiter import rate_limited_batch, simple_sleep

# === Initialize Logger ===
logger = get_shared_logger(LoggerConfig(name="ncbi_client"))

# ========================================================= #
# NCBI E-utilities Client                                   #
# ========================================================= #

class NCBIBackend(ABC):
    """Abstract base class for NCBI backends."""

    @abstractmethod
    def search_by_doi(self, doi: str, email: str, api_key: str | None = None) -> str | None:
        """Search PubMed by DOI, return PMID if found."""
        pass

    @abstractmethod
    def fetch_xml(self, pmid: str, email: str, api_key: str | None = None) -> str | None:
        """Fetch XML data for a given PMID."""
        pass


class HTTPBackend(NCBIBackend):
    """HTTP-based backend using requests library."""

    BASE_URL = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'

    def __init__(self):
        self.session = requests.Session()

    def search_by_doi(self, doi: str, email: str, api_key: str | None = None) -> str | None:
        """Search using HTTP API."""
        url = f'{self.BASE_URL}/esearch.fcgi'
        params = {
            'db': 'pubmed',
            'term': f'{doi}[DOI]',
            'email': email,
            'retmode': 'json'
        }

        if api_key:
            params['api_key'] = api_key

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            id_list = data.get('esearchresult', {}).get('idlist', [])
            return id_list[0] if id_list else None

        except requests.RequestException as e:
            print(f'  ERROR: HTTP search failed: {e}')
            return None

    def fetch_xml(self, pmid: str, email: str, api_key: str | None = None) -> str | None:
        """Fetch XML using HTTP API."""
        url = f'{self.BASE_URL}/efetch.fcgi'
        params = {
            'db': 'pubmed',
            'id': pmid,
            'retmode': 'xml',
            'email': email
        }

        if api_key:
            params['api_key'] = api_key

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.text

        except requests.RequestException as e:
            print(f'  ERROR: HTTP fetch failed: {e}')
            return None


class CLIBackend(NCBIBackend):
    """CLI-based backend using E-utilities command-line tools."""

    def __init__(self):
        """Initialize CLI backend and verify tools."""
        self._ensure_tools_in_path()
        self._verify_tools()

    def _ensure_tools_in_path(self):
        """Ensure E-utilities CLI tools are in PATH."""
        edirect_path = Path.home() / 'edirect'
        if edirect_path.exists():
            current_path = os.environ.get('PATH', '')
            edirect_str = str(edirect_path)
            if edirect_str not in current_path:
                os.environ['PATH'] = f'{edirect_str}:{current_path}'

    def _verify_tools(self):
        """Verify required CLI tools are available."""
        import shutil
        required_tools = ['esearch', 'efetch']
        missing = [tool for tool in required_tools if not shutil.which(tool)]

        if missing:
            raise RuntimeError(
                f'CLI backend requires E-utilities tools. Missing: {', '.join(missing)}\n'
                f'Install from: ftp://ftp.ncbi.nlm.nih.gov/entrez/entrezdirect/'
            )

    def search_by_doi(self, doi: str, email: str, api_key: str | None = None) -> str | None:
        """Search using CLI tools."""
        cmd = [
            'esearch',
            '-db', 'pubmed',
            '-email', email,
            '-query', f'{doi}[DOI]'
        ]

        if api_key:
            cmd.extend(['-api_key', api_key])

        try:
            # Run esearch
            search_result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )

            # Pipe to efetch to get UID
            fetch_result = subprocess.run(
                ['efetch', '-format', 'uid'],
                input=search_result.stdout,
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )

            pmid = fetch_result.stdout.strip()
            return pmid if pmid else None

        except subprocess.CalledProcessError as e:
            print(f'  ERROR: CLI search failed: {e}')
            if e.stderr:
                print(f'  stderr: {e.stderr}')
            return None
        except Exception as e:
            print(f'  ERROR: {e}')
            return None

    def fetch_xml(self, pmid: str, email: str, api_key: str | None = None) -> str | None:
        """Fetch XML using CLI tools."""
        cmd = [
            'efetch',
            '-db', 'pubmed',
            '-id', pmid,
            '-format', 'xml'
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )

            xml_content = result.stdout.strip()

            # Check for CLI tool errors
            if xml_content.startswith('Unable to locate'):
                print('  ERROR: Missing CLI tool component')
                return None

            return xml_content if xml_content else None

        except subprocess.CalledProcessError as e:
            print(f'  ERROR: CLI fetch failed: {e}')
            return None


class NCBIClient:
    """NCBI E-utilities client with HTTP and CLI backend support."""

    def __init__(
        self,
        email: str,
        api_key: str | None = None,
        use_cli: bool = False
    ):
        """
        Initialize NCBI client
        
        args:
            email: Email address (required by NCBI)
            api_key: Optional API key for higher rate limits
            use_cli: If True, use CLI tools; if False (default), use HTTP API
        """
        self.email = email
        self.api_key = api_key

        # Select backend
        if use_cli:
            try:
                self.backend = CLIBackend()
                print('  Using CLI backend')
            except RuntimeError as e:
                print(f'  WARNING: {e}')
                print('  Falling back to HTTP backend')
                self.backend = HTTPBackend()
        else:
            self.backend = HTTPBackend()

    def search_by_doi(self, doi: str) -> str | None:
        """
        Search PubMed by DOI, return PMID.
        
        Args:
            doi: Document Object Identifier
            
        Returns:
            PMID string if found, None otherwise
        """
        return self.backend.search_by_doi(doi, self.email, self.api_key)

    def fetch_reference(self, pmid: str) -> Reference | None:
        """
        Fetch full reference data by PMID.
        
        Args:
            pmid: PubMed ID
            
        Returns:
            Reference object if successful, None otherwise
        """
        xml_string = self.backend.fetch_xml(pmid, self.email, self.api_key)

        if not xml_string:
            return None

        return self._parse_pubmed_xml(xml_string)

    @rate_limited_batch(batch_size=5, sleep_seconds=2.0)
    def fetch_references(self, pmids: list[str]) -> list[Reference]:
        """
        Fetch full Reference objects for a list of PMIDs with rate limiting.

        Args:
            pmids: List of PubMed IDs

        Returns:
            List of Reference objects
        """
        result = []
        for pmid in pmids:
            ref = self.fetch_reference(pmid)
            if ref:
                result.append(ref)
        return result

    def search_pubmed(self, query: str, max_results: int = 20,
                      year_from: int | None = None,
                      year_to: int | None = None):
        """
        Search PubMed and return a list of PMIDs.

        Args:
            query: Search terms
            max_results: Maximum number of results
            year_from: Filter by publication year (from)
            year_to: Filter by publication year (to)

        Returns:
            List of PMIDs
        """
        service = PubMedSearchService(email=self.email, api_key=self.api_key)
        return service.search(
            query=query,
            max_results=max_results,
            year_from=year_from,
            year_to=year_to,
        )

    def _parse_pubmed_xml(self, xml_string: str) -> Reference | None:
        """
        Parse PubMed XML to Reference model.
        
        Args:
            xml_string: XML response from NCBI
            
        Returns:
            Reference object if parsing successful, None otherwise
        """
        try:
            root = ET.fromstring(xml_string)
        except ET.ParseError as e:
            print(f'  ERROR: XML parse error: {e}')
            return None

        article = root.find('.//PubmedArticle')

        if article is None:
            print('  ERROR: No PubmedArticle found in XML')
            return None

        # Extract PMID
        pmid_elem = article.find('.//PMID')
        pmid = pmid_elem.text if pmid_elem is not None else ''

        # Extract DOI
        doi_elem = article.find(".//ArticleId[@IdType='doi']")
        doi = doi_elem.text if doi_elem is not None else ''

        # Extract title
        title_elem = article.find('.//ArticleTitle')
        title = title_elem.text if title_elem is not None else 'No title'

        # Extract authors
        authors = []
        author_list = article.findall('.//Author')
        for author_elem in author_list:
            last_name_elem = author_elem.find('LastName')
            first_name_elem = author_elem.find('ForeName')
            initials_elem = author_elem.find('Initials')

            if last_name_elem is not None:
                authors.append(Author(
                    last_name=last_name_elem.text,
                    first_name=first_name_elem.text if first_name_elem is not None else None,
                    initials=initials_elem.text if initials_elem is not None else None
                ))

        # Extract journal info
        journal_elem = article.find('.//Journal')
        journal_title = 'Unknown'
        journal_abbr = None
        volume = None
        issue = None

        if journal_elem is not None:
            title_elem = journal_elem.find('.//Title')
            if title_elem is not None:
                journal_title = title_elem.text

            abbr_elem = journal_elem.find('.//ISOAbbreviation')
            if abbr_elem is not None:
                journal_abbr = abbr_elem.text

            vol_elem = journal_elem.find('.//Volume')
            if vol_elem is not None:
                volume = vol_elem.text

            iss_elem = journal_elem.find('.//Issue')
            if iss_elem is not None:
                issue = iss_elem.text

        journal = Journal(
            title=journal_title,
            abbreviation=journal_abbr,
            volume=volume,
            issue=issue
        )

        # Extract publication date
        pub_date = None
        date_elem = article.find('.//PubDate')
        if date_elem is not None:
            year_elem = date_elem.find('Year')
            month_elem = date_elem.find('Month')
            day_elem = date_elem.find('Day')

            if year_elem is not None:
                try:
                    year = int(year_elem.text)
                    month = self._month_to_int(month_elem.text) if month_elem is not None else 1
                    day = int(day_elem.text) if day_elem is not None else 1
                    pub_date = datetime(year=year, month=month, day=day).date()
                except (ValueError, AttributeError):
                    pass

        # Extract abstract
        abstract = None
        abstract_elem = article.find('.//AbstractText')
        if abstract_elem is not None:
            abstract = abstract_elem.text

        # Extract keywords and MeSH terms
        keywords = [kw.text for kw in article.findall('.//Keyword') if kw.text]
        mesh_terms = [mesh.text for mesh in article.findall('.//DescriptorName') if mesh.text]

        return Reference(
            pmid=pmid,
            doi=doi,
            title=title,
            authors=authors,
            journal=journal,
            publication_date=pub_date,
            abstract=abstract,
            keywords=keywords,
            mesh_terms=mesh_terms
        )

    @staticmethod
    def _month_to_int(month_str: str) -> int:
        """Convert month abbreviation to integer."""
        months = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
            'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
            'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        return months.get(month_str, 1)
