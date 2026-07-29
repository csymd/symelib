"""
tests/unit/services/test_crossref_client.py
"""

from elib.services.crossref_client import crossref_message_to_reference

SAMPLE_MESSAGE = {
    "DOI": "10.1038/nature12373",
    "title": ["A sample Crossref title"],
    "author": [
        {"family": "Doe", "given": "Jane"},
        {"family": "Roe", "given": "John Q"},
    ],
    "container-title": ["Nature"],
    "short-container-title": ["Nature"],
    "volume": "500",
    "issue": "7463",
    "ISSN": ["0028-0836"],
    "issued": {"date-parts": [[2013, 7, 11]]},
    "abstract": "<jats:p>This is an <i>abstract</i> with tags.</jats:p>",
    "subject": ["Multidisciplinary"],
}


def test_crossref_message_to_reference():
    ref = crossref_message_to_reference(SAMPLE_MESSAGE)
    assert ref is not None
    assert ref.doi == "10.1038/nature12373"
    assert ref.title == "A sample Crossref title"
    assert len(ref.authors) == 2
    assert ref.authors[0].last_name == "Doe"
    assert ref.authors[0].first_name == "Jane"
    assert ref.journal.title == "Nature"
    assert ref.journal.volume == "500"
    assert ref.publication_date is not None
    assert ref.publication_date.year == 2013
    assert ref.abstract is not None
    assert "<" not in ref.abstract
    assert "abstract" in ref.abstract.lower()
    assert "Multidisciplinary" in ref.keywords
