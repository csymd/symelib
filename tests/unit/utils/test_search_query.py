"""
tests/unit/utils/test_search_query.py
"""

from symworx_elibrary.models.metadata import SearchField
from symworx_elibrary.utils.search_query import build_fts_match


def test_prefix_single_token():
    assert build_fts_match("cardio") == "cardio*"


def test_prefix_multi_token_and():
    q = build_fts_match("heart rate")
    assert "heart*" in q
    assert "rate*" in q


def test_title_field_column():
    q = build_fts_match("cardio", SearchField.title)
    assert q == "title:cardio*"


def test_keywords_field():
    q = build_fts_match("gene", SearchField.keywords)
    assert q == "keywords_json:gene*"


def test_quoted_phrase_no_star():
    q = build_fts_match('"heart rate"')
    assert '"heart rate"' in q
    assert "*" not in q or q.count("*") == 0


def test_boolean_expands_tokens():
    q = build_fts_match("cardio OR diabetes")
    assert "cardio*" in q
    assert "diabetes*" in q
    assert "OR" in q


def test_empty():
    assert build_fts_match("") is None
    assert build_fts_match("   ") is None
