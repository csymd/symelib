"""
NCBI E-utilities client with HTTP and CLI backend support.
"""

from abc import ABC, abstractmethod
import os
from pathlib import Path
import subprocess
import time

import requests

from elib.models.reference import Reference
from elib.services.pubmed_xml import parse_first_pubmed_article
from elib.services.search_pubmed import PubMedSearchService
from elib.utils.doi_parser import normalize_doi
from elib.utils.logging import LoggerConfig, get_shared_logger
from elib.utils.rate_limiter import configure_ncbi_throttle, ncbi_throttle, rate_limited_batch

# === Initialize Logger ===
logger = get_shared_logger(LoggerConfig(name="ncbi_client"))


def _ncbi_get(session: requests.Session, url: str, params: dict, *, max_retries: int = 5):
    """GET with shared throttle + exponential backoff on HTTP 429."""
    throttle = ncbi_throttle()
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        throttle.wait()
        try:
            response = session.get(url, params=params, timeout=30)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                ra = float(retry_after) if retry_after and retry_after.isdigit() else None
                sleep_s = throttle.on_rate_limit(ra)
                print(f"  NCBI 429 (too many requests) — sleeping {sleep_s:.1f}s…")
                time.sleep(sleep_s)
                continue
            response.raise_for_status()
            throttle.on_success()
            return response
        except requests.RequestException as e:
            last_exc = e
            # Transient network: brief pause
            if attempt + 1 < max_retries:
                time.sleep(1.0 + attempt)
                continue
            raise
    if last_exc:
        raise last_exc
    return None


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

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self):
        self.session = requests.Session()

    def search_by_doi(self, doi: str, email: str, api_key: str | None = None) -> str | None:
        """Search using HTTP API (throttled; retries 429)."""
        url = f"{self.BASE_URL}/esearch.fcgi"
        params = {"db": "pubmed", "term": f"{doi}[DOI]", "email": email, "retmode": "json"}

        if api_key:
            params["api_key"] = api_key

        try:
            response = _ncbi_get(self.session, url, params)
            if response is None:
                return None
            data = response.json()
            id_list = data.get("esearchresult", {}).get("idlist", [])
            return id_list[0] if id_list else None

        except requests.RequestException as e:
            print(f"  ERROR: HTTP search failed: {e}")
            return None

    def fetch_xml(self, pmid: str, email: str, api_key: str | None = None) -> str | None:
        """Fetch XML using HTTP API (throttled; retries 429)."""
        url = f"{self.BASE_URL}/efetch.fcgi"
        params = {"db": "pubmed", "id": pmid, "retmode": "xml", "email": email}

        if api_key:
            params["api_key"] = api_key

        try:
            response = _ncbi_get(self.session, url, params)
            if response is None:
                return None
            return response.text

        except requests.RequestException as e:
            print(f"  ERROR: HTTP fetch failed: {e}")
            return None


class CLIBackend(NCBIBackend):
    """CLI-based backend using E-utilities command-line tools."""

    def __init__(self):
        """Initialize CLI backend and verify tools."""
        self._ensure_tools_in_path()
        self._verify_tools()

    def _ensure_tools_in_path(self):
        """Ensure E-utilities CLI tools are in PATH."""
        edirect_path = Path.home() / "edirect"
        if edirect_path.exists():
            current_path = os.environ.get("PATH", "")
            edirect_str = str(edirect_path)
            if edirect_str not in current_path:
                os.environ["PATH"] = f"{edirect_str}:{current_path}"

    def _verify_tools(self):
        """Verify required CLI tools are available."""
        import shutil

        required_tools = ["esearch", "efetch"]
        missing = [tool for tool in required_tools if not shutil.which(tool)]

        if missing:
            raise RuntimeError(
                f"CLI backend requires E-utilities tools. Missing: {', '.join(missing)}\n"
                f"Install from: ftp://ftp.ncbi.nlm.nih.gov/entrez/entrezdirect/"
            )

    def search_by_doi(self, doi: str, email: str, api_key: str | None = None) -> str | None:
        """Search using CLI tools."""
        cmd = ["esearch", "-db", "pubmed", "-email", email, "-query", f"{doi}[DOI]"]

        if api_key:
            cmd.extend(["-api_key", api_key])

        try:
            # Run esearch
            search_result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, timeout=30
            )

            # Pipe to efetch to get UID
            fetch_result = subprocess.run(
                ["efetch", "-format", "uid"],
                input=search_result.stdout,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )

            pmid = fetch_result.stdout.strip()
            return pmid if pmid else None

        except subprocess.CalledProcessError as e:
            print(f"  ERROR: CLI search failed: {e}")
            if e.stderr:
                print(f"  stderr: {e.stderr}")
            return None
        except Exception as e:
            print(f"  ERROR: {e}")
            return None

    def fetch_xml(self, pmid: str, email: str, api_key: str | None = None) -> str | None:
        """Fetch XML using CLI tools."""
        cmd = ["efetch", "-db", "pubmed", "-id", pmid, "-format", "xml"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)

            xml_content = result.stdout.strip()

            # Check for CLI tool errors
            if xml_content.startswith("Unable to locate"):
                print("  ERROR: Missing CLI tool component")
                return None

            return xml_content if xml_content else None

        except subprocess.CalledProcessError as e:
            print(f"  ERROR: CLI fetch failed: {e}")
            return None


class NCBIClient:
    """NCBI E-utilities client with HTTP and CLI backend support."""

    def __init__(self, email: str, api_key: str | None = None, use_cli: bool = False):
        """
        Initialize NCBI client

        args:
            email: Email address (required by NCBI)
            api_key: Optional API key for higher rate limits
            use_cli: If True, use CLI tools; if False (default), use HTTP API
        """
        self.email = email
        self.api_key = api_key
        configure_ncbi_throttle(api_key=api_key)

        # Select backend
        if use_cli:
            try:
                self.backend = CLIBackend()
                print("  Using CLI backend")
            except RuntimeError as e:
                print(f"  WARNING: {e}")
                print("  Falling back to HTTP backend")
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
        normalized = normalize_doi(doi) or doi
        return self.backend.search_by_doi(normalized, self.email, self.api_key)

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

        return parse_first_pubmed_article(xml_string)

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

    def search_pubmed(
        self,
        query: str,
        max_results: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ):
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
