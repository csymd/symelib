"""
src/elib/search/search_pubmed.py
"""

import requests

from elib.models.reference import Reference
from elib.services.pubmed_xml import parse_pubmed_xml
from elib.utils.logging import LoggerConfig, get_shared_logger

# === Initialize Logger ===
logger = get_shared_logger(LoggerConfig(name="pubmed_search"))

# ========================================================= #
# PubMed Search Service                                     #
# ========================================================= #


class PubMedSearchResult:
    """Result from PubMed search with metadata."""

    def __init__(self, reference: Reference, in_library: bool = False):
        self.reference = reference
        self.in_library = in_library  # Is this already in local library?


class PubMedSearchService:
    """Search PubMed database via E-utilities API."""

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, email: str, api_key: str | None = None):
        self.email = email
        self.api_key = api_key
        self.session = requests.Session()

    def search(
        self,
        query: str,
        max_results: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[str]:
        """Search PubMed and return list of PMIDs.

        Args:
            query: Search terms
            max_results: Maximum number of results
            year_from: Filter by publication year (from)
            year_to: Filter by publication year (to)

        Returns:
            List of PMIDs
        """
        logger.info("Starting PubMed search", query=query, max_results=max_results)

        # Build search query with filters
        search_query = query

        if year_from and year_to:
            search_query += f" AND {year_from}:{year_to}[pdat]"
        elif year_from:
            search_query += f" AND {year_from}:3000[pdat]"
        elif year_to:
            search_query += f" AND 1900:{year_to}[pdat]"

        url = f"{self.BASE_URL}/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": search_query,
            "retmax": max_results,
            "email": self.email,
            "retmode": "json",
        }

        if self.api_key:
            params["api_key"] = self.api_key

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            pmids = data.get("esearchresult", {}).get("idlist", [])

            logger.info("PubMed search complete", query=query, pmid_count=len(pmids))

            return pmids

        except Exception as e:
            logger.error("PubMed search failed", error=str(e), query=query)
            return []

    def fetch_references(self, pmids: list[str]) -> list[Reference]:
        """Fetch full reference details for PMIDs.

        Args:
            pmids: List of PubMed IDs

        Returns:
            List of Reference objects
        """
        if not pmids:
            return []

        logger.info("Fetching PubMed references", pmid_count=len(pmids))

        # Join PMIDs with commas for bulk fetch
        pmid_string = ",".join(pmids)

        url = f"{self.BASE_URL}/efetch.fcgi"
        params = {"db": "pubmed", "id": pmid_string, "retmode": "xml", "email": self.email}

        if self.api_key:
            params["api_key"] = self.api_key

        try:
            response = self.session.get(url, params=params, timeout=60)
            response.raise_for_status()

            references = parse_pubmed_xml(response.text)

            logger.info("References fetched", count=len(references))

            return references

        except Exception as e:
            logger.error("Failed to fetch references", error=str(e), pmid_count=len(pmids))
            return []
