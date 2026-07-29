"""
tests/unit/services/test_sort.py — year / author / title sorting
"""

from datetime import date
from pathlib import Path

import pytest

from elib.models.metadata import (
    MetadataSource,
    MetadataStatus,
    SearchQuery,
    SortBy,
    SortOrder,
    sort_sql_clause,
)
from elib.models.reference import Author, Journal, Reference
from elib.services.db_manager import DatabaseManager


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(tmp_path / "sort.db")


def _add(db: DatabaseManager, tmp: Path, n: int, last: str, year: int, title: str) -> int:
    pdf = tmp / f"{n}.pdf"
    pdf.write_bytes(b"%PDF")
    ref = Reference(
        pmid=str(1000 + n),
        doi=f"10.1/sort.{n}",
        title=title,
        authors=[Author(last_name=last, first_name="X", initials="X")],
        journal=Journal(title="J"),
        publication_date=date(year, 1, 1),
        abstract="abs",
        keywords=[],
        mesh_terms=[],
    )
    return db.add_document(
        ref,
        file_path=pdf,
        filename=pdf.name,
        file_size=4,
        metadata_status=MetadataStatus.complete,
        metadata_source=MetadataSource.pubmed,
    )


def test_sort_sql_clause_safe():
    assert "publication_year" in sort_sql_clause(SortBy.year, SortOrder.desc)
    assert "json_extract" in sort_sql_clause(SortBy.author, SortOrder.asc)
    assert "relevance" in sort_sql_clause(SortBy.relevance, SortOrder.desc, use_fts=True)


def test_list_documents_by_author(db: DatabaseManager, tmp_path: Path):
    _add(db, tmp_path, 1, "Zebra", 2020, "Z paper")
    _add(db, tmp_path, 2, "Apple", 2019, "A paper")
    _add(db, tmp_path, 3, "Mango", 2021, "M paper")
    docs = db.list_documents(sort_by=SortBy.author, sort_order=SortOrder.asc)
    lasts = []
    import json

    for d in docs:
        lasts.append(json.loads(d.authors_json)[0]["last_name"])
    assert lasts == ["Apple", "Mango", "Zebra"]


def test_list_documents_by_year(db: DatabaseManager, tmp_path: Path):
    _add(db, tmp_path, 1, "A", 2018, "old")
    _add(db, tmp_path, 2, "B", 2022, "new")
    docs = db.list_documents(sort_by=SortBy.year, sort_order=SortOrder.desc)
    assert [d.publication_year for d in docs] == [2022, 2018]


def test_search_sort_author(db: DatabaseManager, tmp_path: Path):
    _add(db, tmp_path, 1, "Zebra", 2020, "Risk study alpha")
    _add(db, tmp_path, 2, "Apple", 2019, "Risk study beta")
    results = db.search(
        SearchQuery(
            text="Risk",
            sort_by=SortBy.author,
            sort_order=SortOrder.asc,
            limit=20,
        )
    )
    import json

    lasts = [json.loads(r.metadata.authors_json)[0]["last_name"] for r in results]
    assert lasts == ["Apple", "Zebra"]


def test_list_items_sort_year(db: DatabaseManager, tmp_path: Path):
    db.create_paper_list("L")
    id1 = _add(db, tmp_path, 1, "A", 2010, "Older")
    id2 = _add(db, tmp_path, 2, "B", 2020, "Newer")
    db.add_to_list(list_name="L", document_id=id1)
    db.add_to_list(list_name="L", document_id=id2)
    items = db.get_list_items(list_name="L", sort_by=SortBy.year, sort_order=SortOrder.desc)
    years = [i.document.publication_year for i in items if i.document]
    assert years == [2020, 2010]
