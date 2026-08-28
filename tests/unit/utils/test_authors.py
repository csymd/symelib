"""
tests/unit/utils/test_authors.py
"""

import pytest

from symworx_elibrary.models.reference import Author
from symworx_elibrary.utils.authors import (
    format_authors_editable,
    parse_authors_editable,
    validate_publication_year,
)


def test_parse_last_first_semicolon():
    authors = parse_authors_editable("Smith, Ada; Jones, Bob")
    assert [a.last_name for a in authors] == ["Smith", "Jones"]
    assert authors[0].first_name == "Ada"
    assert authors[0].initials == "A"
    assert authors[1].first_name == "Bob"


def test_parse_last_name_only():
    authors = parse_authors_editable("Curie")
    assert len(authors) == 1
    assert authors[0].last_name == "Curie"
    assert authors[0].first_name is None


def test_parse_rejects_empty():
    with pytest.raises(ValueError, match="At least one author"):
        parse_authors_editable("  ;  ; ")
    with pytest.raises(ValueError, match="At least one author"):
        parse_authors_editable("")


def test_format_round_trip():
    original = [Author(last_name="van der Waals", first_name="Johannes", initials="J")]
    text = format_authors_editable(original)
    assert text == "van der Waals, Johannes"
    back = parse_authors_editable(text)
    assert back[0].last_name == "van der Waals"
    assert back[0].first_name == "Johannes"


def test_format_from_json():
    text = format_authors_editable('[{"last_name": "Doe", "first_name": "Jane"}]')
    assert text == "Doe, Jane"


def test_validate_publication_year():
    assert validate_publication_year(2020) == 2020
    with pytest.raises(ValueError):
        validate_publication_year(12)
    with pytest.raises(ValueError):
        validate_publication_year(9999)
