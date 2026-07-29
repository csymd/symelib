"""
SQLite persistence for elib (split package).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3

from elib.models.metadata import (
    DocumentMetadata,
    MetadataIssue,
    MetadataSource,
    MetadataStatus,
    SearchField,
    SearchQuery,
    SearchResult,
    SortBy,
    SortOrder,
    classify_metadata_status,
    has_real_doi,
    is_synthetic_doi,
    is_synthetic_pmid,
    sort_sql_clause,
)
from elib.models.paper_list import PaperList, PaperListItem
from elib.models.reference import Reference
from elib.utils.logging import LoggerConfig, get_shared_logger

logger = get_shared_logger(LoggerConfig(name="db_manager"))

_DOCUMENTS_EXTRA_COLUMNS: list[tuple[str, str]] = [
    ("metadata_status", "TEXT NOT NULL DEFAULT 'pending'"),
    ("metadata_source", "TEXT"),
    ("metadata_checked_at", "TIMESTAMP"),
    ("metadata_issue", "TEXT DEFAULT 'unknown'"),
    ("metadata_detail", "TEXT"),
    ("text_extract_chars", "INTEGER"),
    ("source_path", "TEXT"),
    ("original_filename", "TEXT"),
]

from elib.services.db.base import DatabaseBase


class PaperListsMixin:
    """Named paper lists and membership."""

    def create_paper_list(self, name: str, description: str | None = None) -> PaperList:
        """Create a named paper list. Raises sqlite3.IntegrityError if name exists."""
        name = name.strip()
        if not name:
            raise ValueError("List name must not be empty")
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO paper_lists (name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, description, now, now),
            )
            conn.commit()
            list_id = cursor.lastrowid
        result = self.get_paper_list(list_id=list_id)
        assert result is not None
        return result

    def get_paper_list(
        self,
        *,
        list_id: int | None = None,
        name: str | None = None,
        include_deleted: bool = False,
    ) -> PaperList | None:
        if list_id is None and name is None:
            raise ValueError("Provide list_id or name")
        deleted_clause = "" if include_deleted else " AND pl.deleted_at IS NULL"
        with self.get_connection() as conn:
            if list_id is not None:
                row = conn.execute(
                    f"""
                    SELECT pl.*,
                           (SELECT COUNT(*) FROM paper_list_items i WHERE i.list_id = pl.id) AS item_count
                    FROM paper_lists pl
                    WHERE pl.id = ?{deleted_clause}
                    """,
                    (list_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    f"""
                    SELECT pl.*,
                           (SELECT COUNT(*) FROM paper_list_items i WHERE i.list_id = pl.id) AS item_count
                    FROM paper_lists pl
                    WHERE pl.name = ?{deleted_clause}
                    """,
                    (name,),
                ).fetchone()
            if not row:
                return None
            return self._row_to_paper_list(row)

    def list_paper_lists(self, *, include_deleted: bool = False) -> list[PaperList]:
        deleted_clause = "" if include_deleted else " WHERE pl.deleted_at IS NULL"
        with self.get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT pl.*,
                       (SELECT COUNT(*) FROM paper_list_items i WHERE i.list_id = pl.id) AS item_count
                FROM paper_lists pl
                {deleted_clause}
                ORDER BY pl.name COLLATE NOCASE
                """
            ).fetchall()
            return [self._row_to_paper_list(r) for r in rows]

    def rename_paper_list(
        self,
        *,
        list_id: int | None = None,
        name: str | None = None,
        new_name: str | None = None,
        description: str | None = None,
    ) -> PaperList | None:
        """
        Rename and/or update description of a paper list.

        Raises:
            ValueError: empty new name
            sqlite3.IntegrityError: new name already taken
        """
        pl = self.get_paper_list(list_id=list_id, name=name)
        if pl is None or pl.id is None:
            return None
        updates = []
        params: list = []
        if new_name is not None:
            cleaned = new_name.strip()
            if not cleaned:
                raise ValueError("List name cannot be empty")
            if cleaned != pl.name:
                updates.append("name = ?")
                params.append(cleaned)
        if description is not None:
            # Allow clearing description with ""
            desc = description.strip() if description.strip() else None
            updates.append("description = ?")
            params.append(desc)
        if not updates:
            return pl
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(pl.id)
        with self.get_connection() as conn:
            try:
                conn.execute(
                    f"UPDATE paper_lists SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
                raise
        return self.get_paper_list(list_id=pl.id)

    def soft_delete_paper_list(
        self, *, list_id: int | None = None, name: str | None = None
    ) -> bool:
        """Soft-delete a list (hidden from default views; membership preserved)."""
        pl = self.get_paper_list(list_id=list_id, name=name, include_deleted=False)
        if pl is None or pl.id is None:
            return False
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE paper_lists
                SET deleted_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, pl.id),
            )
            conn.commit()
        return True

    def restore_paper_list(self, *, list_id: int | None = None, name: str | None = None) -> bool:
        """Undo soft-delete."""
        pl = self.get_paper_list(list_id=list_id, name=name, include_deleted=True)
        if pl is None or pl.id is None or not pl.is_deleted:
            return False
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE paper_lists
                SET deleted_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (datetime.now().isoformat(), pl.id),
            )
            conn.commit()
        return True

    def delete_paper_list(
        self,
        *,
        list_id: int | None = None,
        name: str | None = None,
        hard: bool = False,
    ) -> bool:
        """
        Delete a list.

        Default is **soft** delete (``deleted_at`` set). Pass ``hard=True`` to
        permanently remove the list and its membership rows (documents stay).
        """
        if not hard:
            return self.soft_delete_paper_list(list_id=list_id, name=name)

        pl = self.get_paper_list(list_id=list_id, name=name, include_deleted=True)
        if pl is None or pl.id is None:
            return False
        with self.get_connection() as conn:
            conn.execute("DELETE FROM paper_list_items WHERE list_id = ?", (pl.id,))
            conn.execute("DELETE FROM paper_lists WHERE id = ?", (pl.id,))
            conn.commit()
        return True

    def add_to_list(
        self,
        *,
        list_id: int | None = None,
        list_name: str | None = None,
        document_id: int | None = None,
        doi: str | None = None,
        notes: str | None = None,
    ) -> PaperListItem | None:
        pl = self.get_paper_list(list_id=list_id, name=list_name)
        if pl is None or pl.id is None:
            return None

        if document_id is None and doi:
            doc = self.get_by_doi(doi)
            if doc is None or doc.id is None:
                return None
            document_id = doc.id
        if document_id is None:
            raise ValueError("Provide document_id or doi")

        doc = self.get_by_id(document_id)
        if doc is None:
            return None

        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO paper_list_items (list_id, document_id, notes, added_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(list_id, document_id) DO UPDATE SET
                    notes = COALESCE(excluded.notes, paper_list_items.notes)
                """,
                (pl.id, document_id, notes, now),
            )
            conn.execute(
                "UPDATE paper_lists SET updated_at = ? WHERE id = ?",
                (now, pl.id),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT * FROM paper_list_items
                WHERE list_id = ? AND document_id = ?
                """,
                (pl.id, document_id),
            ).fetchone()
        return PaperListItem(
            list_id=pl.id,
            document_id=document_id,
            notes=row["notes"] if row else notes,
            added_at=row["added_at"] if row else now,
            document=doc,
        )

    def remove_from_list(
        self,
        *,
        list_id: int | None = None,
        list_name: str | None = None,
        document_id: int | None = None,
        doi: str | None = None,
    ) -> bool:
        pl = self.get_paper_list(list_id=list_id, name=list_name)
        if pl is None or pl.id is None:
            return False
        if document_id is None and doi:
            doc = self.get_by_doi(doi)
            if doc is None or doc.id is None:
                return False
            document_id = doc.id
        if document_id is None:
            raise ValueError("Provide document_id or doi")

        with self.get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM paper_list_items WHERE list_id = ? AND document_id = ?",
                (pl.id, document_id),
            )
            conn.execute(
                "UPDATE paper_lists SET updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), pl.id),
            )
            conn.commit()
            return cur.rowcount > 0

    def get_list_items(
        self,
        *,
        list_id: int | None = None,
        list_name: str | None = None,
        sort_by: SortBy = SortBy.added_date,
        sort_order: SortOrder = SortOrder.desc,
    ) -> list[PaperListItem]:
        pl = self.get_paper_list(list_id=list_id, name=list_name)
        if pl is None or pl.id is None:
            return []
        # For list membership, "added_date" means when added to the list
        if sort_by == SortBy.added_date:
            order = "ASC" if sort_order == SortOrder.asc else "DESC"
            order_sql = f" ORDER BY i.added_at {order}"
        elif sort_by == SortBy.relevance:
            order_sql = " ORDER BY i.added_at DESC"
        else:
            order_sql = sort_sql_clause(sort_by, sort_order, use_fts=False)
        with self.get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT i.list_id, i.document_id, i.notes, i.added_at, d.*
                FROM paper_list_items i
                JOIN documents d ON d.id = i.document_id
                WHERE i.list_id = ?
                {order_sql}
                """,
                (pl.id,),
            ).fetchall()
            items: list[PaperListItem] = []
            for row in rows:
                data = dict(row)
                doc = self._row_to_metadata(row)
                items.append(
                    PaperListItem(
                        list_id=data["list_id"],
                        document_id=data["document_id"],
                        notes=data.get("notes"),
                        added_at=data.get("added_at") or datetime.now(),
                        document=doc,
                    )
                )
            return items

    def lists_for_document(self, document_id: int) -> list[PaperList]:
        """Return all lists that contain a given document."""
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT pl.*,
                       (SELECT COUNT(*) FROM paper_list_items i2 WHERE i2.list_id = pl.id) AS item_count
                FROM paper_lists pl
                JOIN paper_list_items i ON i.list_id = pl.id
                WHERE i.document_id = ?
                ORDER BY pl.name COLLATE NOCASE
                """,
                (document_id,),
            ).fetchall()
            return [self._row_to_paper_list(r) for r in rows]

    def _row_to_paper_list(self, row: sqlite3.Row) -> PaperList:
        data = dict(row)
        return PaperList(
            id=data["id"],
            name=data["name"],
            description=data.get("description"),
            created_at=data.get("created_at") or datetime.now(),
            updated_at=data.get("updated_at") or datetime.now(),
            deleted_at=data.get("deleted_at"),
            item_count=int(data.get("item_count") or 0),
        )
