"""
tests/unit/models/test_reference.py
"""

from datetime import date

from symworx_elibrary.models.reference import Author, Journal, Reference


# Test for Author model
def test_author_format_citation_with_initials():
    author = Author(last_name="Smith", first_name="John", initials="J")
    assert author.format_citation() == "Smith J"


def test_author_format_citation_without_initials():
    author = Author(last_name="Doe", first_name="Jane")
    assert author.format_citation() == "Doe"


# Test for Journal model
def test_journal_creation():
    journal = Journal(
        title="Journal of Testing", abbreviation="J Test", issn="1234-5678", volume="42", issue="7"
    )
    assert journal.title == "Journal of Testing"
    assert journal.abbreviation == "J Test"
    assert journal.issn == "1234-5678"
    assert journal.volume == "42"
    assert journal.issue == "7"


# Test for Reference model
def test_reference_creation():
    author1 = Author(last_name="Smith", first_name="John", initials="J")
    author2 = Author(last_name="Doe", first_name="Jane")
    journal = Journal(
        title="Journal of Testing", abbreviation="J Test", issn="1234-5678", volume="42", issue="7"
    )
    reference = Reference(
        pmid="12345678",
        doi="10.1234/example.doi",
        title="An example of a reference title",
        authors=[author1, author2],
        journal=journal,
        publication_date=date(2023, 10, 15),
        abstract="This is an example abstract.",
        keywords=["example", "testing"],
        mesh_terms=["term1", "term2"],
    )
    assert reference.pmid == "12345678"
    assert reference.doi == "10.1234/example.doi"
    assert reference.title == "An example of a reference title"
    assert len(reference.authors) == 2
    assert reference.authors[0].last_name == "Smith"
    assert reference.journal.title == "Journal of Testing"
    assert reference.publication_date == date(2023, 10, 15)
    assert reference.abstract == "This is an example abstract."
    assert reference.keywords == ["example", "testing"]
    assert reference.mesh_terms == ["term1", "term2"]


def test_reference_first_author_lastname():
    author1 = Author(last_name="Smith", first_name="John", initials="J")
    author2 = Author(last_name="Doe", first_name="Jane")
    journal = Journal(title="Journal of Testing")
    reference = Reference(
        pmid="12345678",
        doi="10.1234/example.doi",
        title="An example of a reference title",
        authors=[author1, author2],
        journal=journal,
    )
    assert reference.first_author_lastname() == "Smith"


def test_reference_first_author_lastname_no_authors():
    journal = Journal(title="Journal of Testing")
    reference = Reference(
        pmid="12345678",
        doi="10.1234/example.doi",
        title="An example of a reference title",
        authors=[],
        journal=journal,
    )
    assert reference.first_author_lastname() == "Unknown"


def test_reference_publication_year():
    journal = Journal(title="Journal of Testing")
    reference = Reference(
        pmid="12345678",
        doi="10.1234/example.doi",
        title="An example of a reference title",
        authors=[],
        journal=journal,
        publication_date=date(2023, 10, 15),
    )
    assert reference.publication_year() == "2023"


def test_reference_publication_year_no_date():
    journal = Journal(title="Journal of Testing")
    reference = Reference(
        pmid="12345678",
        doi="10.1234/example.doi",
        title="An example of a reference title",
        authors=[],
        journal=journal,
    )
    assert reference.publication_year() == "NODATE"


def test_reference_generate_filename():
    author1 = Author(last_name="Smith", first_name="John", initials="J")
    journal = Journal(title="Journal of Testing")
    reference = Reference(
        pmid="12345678",
        doi="10.1234/example.doi",
        title="An example of a reference title with more than five words",
        authors=[author1],
        journal=journal,
        publication_date=date(2023, 10, 15),
    )
    # first five title words only
    expected_filename = "Smith_2023_An_example_of_a_reference.pdf"
    assert reference.generate_filename() == expected_filename
