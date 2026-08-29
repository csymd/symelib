"""
tests/unit/cli/test_search.py
"""

from datetime import date

import pytest
import typer

from symworx_elibrary.cli.search import _parse_iso_date


def test_parse_iso_date_valid():
    assert _parse_iso_date("2026-08-28") == date(2026, 8, 28)
    assert _parse_iso_date(None) is None
    assert _parse_iso_date("") is None


def test_parse_iso_date_invalid():
    with pytest.raises(typer.BadParameter):
        _parse_iso_date("08/28/2026")
    with pytest.raises(typer.BadParameter):
        _parse_iso_date("not-a-date")
