"""
src/elib/search/search_pubmed.py
"""

from typing import List, Optional
from datetime import datetime

import requests

from elib.models.reference import Reference, Author, Journal
from elib.utils.logging import get_shared_logger

logger = get_shared_logger(name="pubmed_search")

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
    
    BASE_URL = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
    
    def __init__(self, email: str, api_key: Optional[str] = None):
        self.email = email
        self.api_key = api_key
        self.session = requests.Session()
    
    def search(
        self,
        query: str,
        max_results: int = 20,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None
    ) -> List[str]:
        '''Search PubMed and return list of PMIDs.
        
        Args:
            query: Search terms
            max_results: Maximum number of results
            year_from: Filter by publication year (from)
            year_to: Filter by publication year (to)
            
        Returns:
            List of PMIDs
        '''
        logger.info('Starting PubMed search', 
                   query=query,
                   max_results=max_results)
        
        # Build search query with filters
        search_query = query
        
        if year_from and year_to:
            search_query += f' AND {year_from}:{year_to}[pdat]'
        elif year_from:
            search_query += f' AND {year_from}:3000[pdat]'
        elif year_to:
            search_query += f' AND 1900:{year_to}[pdat]'
        
        url = f'{self.BASE_URL}/esearch.fcgi'
        params = {
            'db': 'pubmed',
            'term': search_query,
            'retmax': max_results,
            'email': self.email,
            'retmode': 'json'
        }
        
        if self.api_key:
            params['api_key'] = self.api_key
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            pmids = data.get('esearchresult', {}).get('idlist', [])
            
            logger.info('PubMed search complete',
                       query=query,
                       pmid_count=len(pmids))
            
            return pmids
            
        except Exception as e:
            logger.error('PubMed search failed',
                        error=str(e),
                        query=query)
            return []
    
    def fetch_references(self, pmids: List[str]) -> List[Reference]:
        '''Fetch full reference details for PMIDs.
        
        Args:
            pmids: List of PubMed IDs
            
        Returns:
            List of Reference objects
        '''
        if not pmids:
            return []
        
        logger.info('Fetching PubMed references', pmid_count=len(pmids))
        
        # Join PMIDs with commas for bulk fetch
        pmid_string = ','.join(pmids)
        
        url = f'{self.BASE_URL}/efetch.fcgi'
        params = {
            'db': 'pubmed',
            'id': pmid_string,
            'retmode': 'xml',
            'email': self.email
        }
        
        if self.api_key:
            params['api_key'] = self.api_key
        
        try:
            response = self.session.get(url, params=params, timeout=60)
            response.raise_for_status()
            
            # Parse XML and extract references
            references = self._parse_pubmed_xml(response.text)
            
            logger.info('References fetched', count=len(references))
            
            return references
            
        except Exception as e:
            logger.error('Failed to fetch references',
                        error=str(e),
                        pmid_count=len(pmids))
            return []
    
    def _parse_pubmed_xml(self, xml_string: str) -> List[Reference]:
        '''Parse PubMed XML response to Reference objects.'''
        import xml.etree.ElementTree as ET
        
        references = []
        
        try:
            root = ET.fromstring(xml_string)
            articles = root.findall('.//PubmedArticle')
            
            for article in articles:
                try:
                    ref = self._parse_single_article(article)
                    if ref:
                        references.append(ref)
                except Exception as e:
                    logger.warning('Failed to parse article', error=str(e))
                    
        except Exception as e:
            logger.error('XML parsing failed', error=str(e))
        
        return references
    
    def _parse_single_article(self, article) -> Optional[Reference]:
        '''Parse single PubmedArticle XML element.'''
        import xml.etree.ElementTree as ET
        
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
        for author_elem in article.findall('.//Author'):
            last_name = author_elem.find('LastName')
            first_name = author_elem.find('ForeName')
            initials = author_elem.find('Initials')
            
            if last_name is not None:
                authors.append(Author(
                    last_name=last_name.text,
                    first_name=first_name.text if first_name is not None else None,
                    initials=initials.text if initials is not None else None
                ))
        
        # Extract journal
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
        
        # Extract keywords
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
