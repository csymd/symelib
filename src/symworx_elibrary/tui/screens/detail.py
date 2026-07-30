"""
Document detail screen: metadata + abstract + open PDF.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

if TYPE_CHECKING:
    from symworx_elibrary.tui.app import ElibApp


def _escape_markup(text: str) -> str:
    """Escape Rich/Textual markup special characters in free text."""
    return (text or "").replace("[", "\\[").replace("]", "\\]")


class DetailScreen(Screen):
    """Full metadata + abstract for one document."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("b", "go_back", "Back", show=False),
        Binding("o", "open_pdf", "PDF", show=True),
        Binding("a", "add_to_list", "List+", show=True),
        Binding("enter", "open_pdf", "PDF", show=False),
        Binding("t", "app.toggle_theme", "Theme", show=True),
        Binding("ctrl+q", "app.quit", "Quit", show=True, priority=True, key_display="Ctrl+Q"),
    ]

    def __init__(self, document_id: int) -> None:
        super().__init__()
        self.document_id = document_id
        self._file_path: str | None = None

    @property
    def app(self) -> ElibApp:  # type: ignore[override]
        return super().app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]elib[/]  [cyan]detail[/]                     [dim]Esc back · Ctrl+Q quit[/]",
            id="app-header",
        )
        yield Static("  o open PDF  ·  a add to list  ·  Esc back", id="action-bar")
        with VerticalScroll(id="detail-scroll"):
            yield Static("", id="detail-title")
            yield Static("", id="detail-meta")
            yield Static("Abstract", classes="section-label")
            yield Static("", id="detail-abstract")
            yield Static("File  ·  [o] open PDF", classes="section-label")
            yield Static("", id="detail-file")
            yield Static("Lists", classes="section-label")
            yield Static("", id="detail-lists")

    def on_mount(self) -> None:
        self.app.clear_esc_quit()
        self.app.set_action_bar("o open PDF  ·  a add to list  ·  Esc back")
        self._load()

    def _load(self) -> None:
        doc = self.app.db.get_by_id(self.document_id)
        if doc is None:
            self.query_one("#detail-title", Static).update("Document not found")
            return

        self._file_path = doc.file_path
        # Titles/authors may contain [brackets] that break markup
        self.query_one("#detail-title", Static).update(_escape_markup(doc.title))

        authors = _escape_markup(self._format_authors(doc.authors_json))
        status = doc.metadata_status.value if doc.metadata_status else "?"
        source = doc.metadata_source.value if doc.metadata_source else "—"
        year = doc.publication_year or "—"
        journal = _escape_markup(doc.journal or "")
        doi = _escape_markup(doc.doi or "—")
        pmid = _escape_markup(doc.pmid or "—")
        lines = [
            f"[b]Authors[/b]  {authors}",
            f"[b]Journal[/b]  {journal} ({year})",
            f"[b]DOI[/b]      {doi}",
            f"[b]PMID[/b]     {pmid}",
            f"[b]Status[/b]   {status}  via {source}",
        ]
        self.query_one("#detail-meta", Static).update("\n".join(lines))

        abstract = (doc.abstract or "").strip()
        if abstract:
            # Abstracts as plain markup-escaped text (no tags from PubMed labels)
            self.query_one("#detail-abstract", Static).update(_escape_markup(abstract))
        else:
            self.query_one("#detail-abstract", Static).update(
                f"[dim]No abstract available for this record. Try: elib enrich --id {doc.id}[/dim]"
            )

        # Do not use [link=/abs/path] — Rich markup treats "/" after "=" as invalid.
        safe_name = _escape_markup(doc.filename)
        safe_path = _escape_markup(doc.file_path)
        self.query_one("#detail-file", Static).update(
            f"[bold]{safe_name}[/bold]\n"
            f"[dim]{safe_path}[/dim]\n"
            "[cyan]Press o to open in your PDF viewer[/]"
        )

        lists = self.app.db.lists_for_document(self.document_id)
        if lists:
            self.query_one("#detail-lists", Static).update(
                _escape_markup(", ".join(pl.name for pl in lists))
            )
        else:
            self.query_one("#detail-lists", Static).update(
                "[dim]Not on any list — press a to add[/dim]"
            )

        self.sub_title = f"id={doc.id}"

    @staticmethod
    def _format_authors(authors_json: str) -> str:
        if not authors_json or authors_json in ("[]", "null"):
            return "—"
        try:
            data = json.loads(authors_json)
        except json.JSONDecodeError:
            return authors_json[:200]
        if not isinstance(data, list):
            return str(data)[:200]
        names = []
        for a in data[:12]:
            if isinstance(a, dict):
                last = a.get("last_name") or ""
                first = a.get("first_name") or a.get("initials") or ""
                names.append(f"{last} {first}".strip())
            elif isinstance(a, str):
                names.append(a)
        extra = f" (+{len(data) - 12})" if len(data) > 12 else ""
        return ", ".join(names) + extra if names else "—"

    def action_go_back(self) -> None:
        self.app.clear_esc_quit()
        self.app.pop_screen()

    def action_open_pdf(self) -> None:
        path = self._file_path
        if not path:
            doc = self.app.db.get_by_id(self.document_id)
            path = doc.file_path if doc else None
        if not path:
            self.notify("No file path on this record", severity="warning")
            return
        ok, msg = self.app.open_pdf(path)
        # Multi-line errors: show first line as toast, rest if short
        first = msg.split("\n", 1)[0]
        self.notify(
            first[:180], severity="information" if ok else "error", timeout=8 if not ok else 3
        )

    def action_add_to_list(self) -> None:
        from symworx_elibrary.tui.screens.library import AddToListModal

        doc = self.app.db.get_by_id(self.document_id)
        title = doc.title if doc else str(self.document_id)
        self.app.push_screen(AddToListModal(self.document_id, title))

    def on_click(self, event) -> None:
        try:
            if getattr(event.widget, "id", None) == "detail-file":
                self.action_open_pdf()
        except Exception:
            pass
