"""
Shared PubMed XML → Reference parsing helpers.
"""

from __future__ import annotations

from datetime import datetime
import xml.etree.ElementTree as ET

from elib.models.reference import Author, Journal, Reference
from elib.utils.doi_parser import normalize_doi


def _element_text(elem: ET.Element | None) -> str | None:
    """Collect all text under an element (handles nested italics etc.)."""
    if elem is None:
        return None
    text = "".join(elem.itertext()).strip()
    return text or None


def extract_abstract(article: ET.Element) -> str | None:
    """
    Build a full abstract from one or more AbstractText nodes.

    Structured PubMed abstracts often split into labeled sections
    (BACKGROUND, METHODS, RESULTS, CONCLUSIONS). Concatenate them.
    """
    parts: list[str] = []
    for abs_elem in article.findall(".//AbstractText"):
        text = _element_text(abs_elem)
        if not text:
            continue
        label = abs_elem.get("Label") or abs_elem.get("NlmCategory")
        if label and label.upper() not in ("UNASSIGNED", "OTHER"):
            parts.append(f"{label}: {text}")
        else:
            parts.append(text)
    if not parts:
        return None
    return "\n\n".join(parts)


def _month_to_int(month_str: str | None) -> int:
    if not month_str:
        return 1
    months = {
        "Jan": 1,
        "Feb": 2,
        "Mar": 3,
        "Apr": 4,
        "May": 5,
        "Jun": 6,
        "Jul": 7,
        "Aug": 8,
        "Sep": 9,
        "Oct": 10,
        "Nov": 11,
        "Dec": 12,
    }
    if month_str in months:
        return months[month_str]
    try:
        return int(month_str)
    except ValueError:
        return 1


def parse_pubmed_article(article: ET.Element) -> Reference | None:
    """Parse a single PubmedArticle element into a Reference."""
    pmid_elem = article.find(".//PMID")
    pmid = (pmid_elem.text or "").strip() if pmid_elem is not None else ""

    doi_elem = article.find(".//ArticleId[@IdType='doi']")
    doi_raw = doi_elem.text if doi_elem is not None else ""
    doi = normalize_doi(doi_raw) or (doi_raw.strip() if doi_raw else "")

    title_elem = article.find(".//ArticleTitle")
    title = _element_text(title_elem) or "No title"

    authors: list[Author] = []
    for author_elem in article.findall(".//Author"):
        last_name_elem = author_elem.find("LastName")
        first_name_elem = author_elem.find("ForeName")
        initials_elem = author_elem.find("Initials")
        if last_name_elem is not None and last_name_elem.text:
            authors.append(
                Author(
                    last_name=last_name_elem.text,
                    first_name=first_name_elem.text if first_name_elem is not None else None,
                    initials=initials_elem.text if initials_elem is not None else None,
                )
            )

    journal_elem = article.find(".//Journal")
    journal_title = "Unknown"
    journal_abbr = None
    volume = None
    issue = None
    if journal_elem is not None:
        t = journal_elem.find(".//Title")
        if t is not None and t.text:
            journal_title = t.text
        abbr = journal_elem.find(".//ISOAbbreviation")
        if abbr is not None:
            journal_abbr = abbr.text
        vol = journal_elem.find(".//Volume")
        if vol is not None:
            volume = vol.text
        iss = journal_elem.find(".//Issue")
        if iss is not None:
            issue = iss.text

    journal = Journal(title=journal_title, abbreviation=journal_abbr, volume=volume, issue=issue)

    pub_date = None
    date_elem = article.find(".//PubDate")
    if date_elem is not None:
        year_elem = date_elem.find("Year")
        month_elem = date_elem.find("Month")
        day_elem = date_elem.find("Day")
        if year_elem is not None and year_elem.text:
            try:
                year = int(year_elem.text)
                month = _month_to_int(month_elem.text if month_elem is not None else None)
                day = int(day_elem.text) if day_elem is not None and day_elem.text else 1
                # Clamp invalid day/month conservatively
                day = max(1, min(day, 28 if month == 2 else 31))
                pub_date = datetime(year=year, month=month, day=day).date()
            except (ValueError, AttributeError):
                pass

    abstract = extract_abstract(article)
    keywords = [kw.text for kw in article.findall(".//Keyword") if kw.text]
    mesh_terms = [mesh.text for mesh in article.findall(".//DescriptorName") if mesh.text]

    # Reference currently requires non-empty doi/pmid strings; use empty when missing.
    return Reference(
        pmid=pmid,
        doi=doi or "",
        title=title,
        authors=authors,
        journal=journal,
        publication_date=pub_date,
        abstract=abstract,
        keywords=keywords,
        mesh_terms=mesh_terms,
    )


def parse_pubmed_xml(xml_string: str) -> list[Reference]:
    """Parse a full PubMed XML response into Reference objects."""
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError:
        return []

    refs: list[Reference] = []
    for article in root.findall(".//PubmedArticle"):
        ref = parse_pubmed_article(article)
        if ref:
            refs.append(ref)
    return refs


def parse_first_pubmed_article(xml_string: str) -> Reference | None:
    """Parse and return the first PubmedArticle in an XML string."""
    refs = parse_pubmed_xml(xml_string)
    return refs[0] if refs else None
