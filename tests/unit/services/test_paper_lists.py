"""
tests/unit/services/test_paper_lists.py
"""

from datetime import date
from pathlib import Path

import pytest

from symworx_elibrary.models.metadata import MetadataSource, MetadataStatus
from symworx_elibrary.models.reference import Author, Journal, Reference
from symworx_elibrary.services.bibtex import citation_key, document_to_bibtex, documents_to_bibtex
from symworx_elibrary.services.db_manager import DatabaseManager


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(tmp_path / "lists.db")


def _add_doc(db: DatabaseManager, tmp_path: Path, n: int, **ref_kw) -> int:
    pdf = tmp_path / f"p{n}.pdf"
    pdf.write_bytes(b"%PDF")
    ref = Reference(
        pmid=str(1000 + n),
        doi=f"10.1234/doc.{n}",
        title=ref_kw.get("title", f"Paper Number {n} About Genes"),
        authors=[Author(last_name="Smith", first_name="Ada", initials="A")],
        journal=Journal(title="Nature"),
        publication_date=date(2020, 1, 1),
        abstract="An abstract for testing bibliographies.",
        keywords=["gene"],
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


def test_create_and_list_paper_lists(db: DatabaseManager):
    pl = db.create_paper_list("R01-2026", description="Grant lit")
    assert pl.id is not None
    assert pl.name == "R01-2026"
    assert pl.item_count == 0

    lists = db.list_paper_lists()
    assert len(lists) == 1
    assert lists[0].description == "Grant lit"


def test_add_remove_show(db: DatabaseManager, tmp_path: Path):
    db.create_paper_list("ms-draft")
    id1 = _add_doc(db, tmp_path, 1)
    _add_doc(db, tmp_path, 2)

    item = db.add_to_list(list_name="ms-draft", document_id=id1, notes="key ref")
    assert item is not None
    assert item.document is not None
    assert item.document.id == id1

    db.add_to_list(list_name="ms-draft", doi="10.1234/doc.2")
    pl = db.get_paper_list(name="ms-draft")
    assert pl is not None
    assert pl.item_count == 2

    items = db.get_list_items(list_name="ms-draft")
    assert len(items) == 2
    assert any(i.notes == "key ref" for i in items)

    assert db.remove_from_list(list_name="ms-draft", document_id=id1)
    assert db.get_paper_list(name="ms-draft").item_count == 1

    assert db.remove_from_list(list_name="ms-draft", doi="10.1234/doc.2")
    assert db.get_paper_list(name="ms-draft").item_count == 0


def test_delete_list_keeps_documents(db: DatabaseManager, tmp_path: Path):
    db.create_paper_list("temp")
    doc_id = _add_doc(db, tmp_path, 1)
    db.add_to_list(list_name="temp", document_id=doc_id)
    # soft-delete by default
    assert db.delete_paper_list(name="temp")
    assert db.get_paper_list(name="temp") is None  # hidden
    assert db.get_paper_list(name="temp", include_deleted=True) is not None
    assert db.get_by_id(doc_id) is not None
    # restore
    assert db.restore_paper_list(name="temp")
    assert db.get_paper_list(name="temp") is not None
    # hard delete
    assert db.delete_paper_list(name="temp", hard=True)
    assert db.get_paper_list(name="temp", include_deleted=True) is None
    assert db.get_by_id(doc_id) is not None


def test_duplicate_list_name(db: DatabaseManager):
    db.create_paper_list("same")
    with pytest.raises(Exception):
        db.create_paper_list("same")


def test_rename_paper_list(db: DatabaseManager, tmp_path: Path):
    db.create_paper_list("old-name", description="v1")
    doc_id = _add_doc(db, tmp_path, 1)
    db.add_to_list(list_name="old-name", document_id=doc_id)

    pl = db.rename_paper_list(name="old-name", new_name="new-name")
    assert pl is not None
    assert pl.name == "new-name"
    assert pl.description == "v1"
    assert pl.item_count == 1
    assert db.get_paper_list(name="old-name") is None
    assert db.get_paper_list(name="new-name") is not None
    # Membership preserved under new name
    items = db.get_list_items(list_name="new-name")
    assert len(items) == 1
    assert items[0].document_id == doc_id

    # Description-only update (same name)
    pl2 = db.rename_paper_list(name="new-name", new_name="new-name", description="updated desc")
    assert pl2 is not None
    assert pl2.name == "new-name"
    assert pl2.description == "updated desc"

    # Clear description
    pl3 = db.rename_paper_list(name="new-name", description="")
    assert pl3 is not None
    assert pl3.description is None

    # Empty name rejected
    with pytest.raises(ValueError, match="empty"):
        db.rename_paper_list(name="new-name", new_name="   ")

    # Duplicate name rejected
    db.create_paper_list("other")
    with pytest.raises(Exception):
        db.rename_paper_list(name="new-name", new_name="other")


def test_bibtex_export(db: DatabaseManager, tmp_path: Path):
    db.create_paper_list("bib")
    _add_doc(db, tmp_path, 1, title="CRISPR Editing in Oncology")
    db.add_to_list(list_name="bib", doi="10.1234/doc.1")
    items = db.get_list_items(list_name="bib")
    docs = [i.document for i in items if i.document]
    bib = documents_to_bibtex(docs)
    assert "@article{" in bib
    assert "Smith" in bib
    assert "2020" in bib
    assert "10.1234/doc.1" in bib
    assert "CRISPR" in bib or "Crsp" in bib or "Editing" in bib

    meta = docs[0]
    key = citation_key(meta)
    assert "Smith" in key
    assert "2020" in key
    entry = document_to_bibtex(meta)
    assert entry.startswith("@article{")
    assert "pmid" in entry.lower() or "1234" in entry
