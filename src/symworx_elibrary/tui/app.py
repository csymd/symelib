"""
elib Textual application entry.

Design notes (mirrors symworx SymView chrome):
  - Cyan accents on dark surface (see elib.tcss)
  - Light beige theme toggle with `t`
  - Esc Esc at root to quit; Ctrl+Q anytime
"""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import App
from textual.binding import Binding

from symworx_elibrary.services.db_manager import DatabaseManager
from symworx_elibrary.tui.screens.library import LibraryScreen
from symworx_elibrary.utils.config import Config
from symworx_elibrary.utils.open_file import open_path


class ElibApp(App[None]):
    """Interactive browser for the local paper library."""

    TITLE = "elib"
    SUB_TITLE = "paper library"
    CSS_PATH = "elib.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True, priority=True, key_display="Ctrl+Q"),
        Binding("t", "toggle_theme", "Theme", show=True),
        Binding("question_mark", "help", "Help", show=False),
    ]

    def __init__(self, db_path: Path, config: Config | None = None, **kwargs):
        super().__init__(**kwargs)
        self.db_path = Path(db_path)
        self.db = DatabaseManager(self.db_path)
        self.config = config or Config.load()
        self.esc_quit_pending: bool = False
        self.light_theme: bool = False

    def on_mount(self) -> None:
        self.push_screen(LibraryScreen())

    def clear_esc_quit(self) -> None:
        self.esc_quit_pending = False

    def arm_esc_quit(self) -> None:
        self.esc_quit_pending = True
        self.notify("Esc again to quit  ·  Ctrl+Q anytime", timeout=3)

    def handle_root_escape(self) -> bool:
        if self.esc_quit_pending:
            self.exit()
            return True
        self.arm_esc_quit()
        return True

    def set_action_bar(self, text: str) -> None:
        try:
            screen = self.screen
            bar = screen.query_one("#action-bar")
            bar.update(f"  {text}")  # type: ignore[union-attr]
        except Exception:
            pass

    def action_toggle_theme(self) -> None:
        """Switch between dark cyan and light beige themes."""
        self.light_theme = not self.light_theme
        self.set_class(self.light_theme, "theme-light")
        label = "light/beige" if self.light_theme else "dark"
        self.notify(f"Theme: {label}", timeout=2)

    def reload_db(self) -> None:
        """Re-open SQLite connection layer (picks up imports from other processes)."""
        self.db = DatabaseManager(self.db_path)

    def open_pdf(self, file_path: str | Path) -> tuple[bool, str]:
        """Open PDF using current config/env viewer preference (reload config each time)."""
        # Pick up pdf_viewer changes without restarting the TUI
        try:
            self.config = Config.load()
        except Exception:
            pass
        viewer = self.config.pdf_viewer or os.environ.get("ELIB_PDF_VIEWER")
        return open_path(file_path, preferred_viewer=viewer)

    def action_help(self) -> None:
        self.notify(
            "/ search · Esc leave search · f/Ctrl+f field · ↓ table · "
            "s sort · o PDF · r refresh · l lists · t theme · Esc Esc / Ctrl+Q quit",
            title="Keys",
            timeout=10,
        )


def run_tui(db_path: Path, config: Config | None = None) -> None:
    """Launch the Textual TUI (blocking)."""
    app = ElibApp(db_path=db_path, config=config)
    app.run()
