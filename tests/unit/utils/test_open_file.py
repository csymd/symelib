"""Unit tests for PDF open helper (Papers + Firefox remote handoff)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import symworx_elibrary.utils.open_file as open_file_mod
from symworx_elibrary.utils.open_file import (
    _build_cmd,
    _file_url,
    _resolve_viewer_spec,
    open_path,
    recommend_pdf_viewer,
)


def test_file_url_quotes_spaces(tmp_path: Path) -> None:
    p = tmp_path / "my paper.pdf"
    p.write_bytes(b"%PDF")
    url = _file_url(p)
    assert url.startswith("file://")
    assert " " not in url
    assert "my%20paper.pdf" in url


def test_build_cmd_firefox_uses_new_tab(tmp_path: Path) -> None:
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF")
    cmd = _build_cmd(["/usr/bin/firefox"], p)
    assert cmd[0] == "/usr/bin/firefox"
    assert "--new-tab" in cmd
    assert "--new-window" not in cmd
    assert cmd[-1] == _file_url(p)


def test_build_cmd_strips_user_new_window(tmp_path: Path) -> None:
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF")
    cmd = _build_cmd(["/usr/bin/firefox", "--new-window"], p)
    assert cmd.count("--new-tab") == 1
    assert "--new-window" not in cmd


def test_build_cmd_native_viewer_uses_path(tmp_path: Path) -> None:
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF")
    cmd = _build_cmd(["/usr/bin/evince"], p)
    assert cmd == ["/usr/bin/evince", str(p.resolve())]


def test_build_cmd_papers_flatpak_uses_path(tmp_path: Path) -> None:
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF")
    cmd = _build_cmd(["/usr/bin/flatpak", "run", "org.gnome.Papers"], p)
    assert cmd == [
        "/usr/bin/flatpak",
        "run",
        "org.gnome.Papers",
        str(p.resolve()),
    ]


def test_resolve_papers_alias() -> None:
    with patch.object(
        open_file_mod,
        "papers_argv",
        return_value=["/usr/bin/flatpak", "run", "org.gnome.Papers"],
    ):
        assert _resolve_viewer_spec("papers") == [
            "/usr/bin/flatpak",
            "run",
            "org.gnome.Papers",
        ]
        assert _resolve_viewer_spec("document-viewer")[0]  # type: ignore[index]
        assert _resolve_viewer_spec("org.gnome.Papers") is not None


def test_resolve_flatpak_run_spec() -> None:
    with patch.object(open_file_mod, "_which", return_value="/usr/bin/flatpak"):
        got = _resolve_viewer_spec("flatpak run org.gnome.Papers")
    assert got == ["/usr/bin/flatpak", "run", "org.gnome.Papers"]


def test_recommend_prefers_papers() -> None:
    with (
        patch.object(open_file_mod, "papers_argv", return_value=["/x/papers"]),
        patch.object(open_file_mod, "_which", return_value="/usr/bin/firefox"),
    ):
        assert recommend_pdf_viewer() == "papers"


def test_open_path_missing_file() -> None:
    ok, msg = open_path("/no/such/file.pdf")
    assert ok is False
    assert "not found" in msg.lower()


def test_open_path_papers_success(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    proc = MagicMock()
    proc.poll.return_value = None  # Papers stays running

    with (
        patch.dict("os.environ", {"DISPLAY": ":0"}, clear=False),
        patch.object(
            open_file_mod,
            "_candidates",
            return_value=[["/usr/bin/flatpak", "run", "org.gnome.Papers"]],
        ),
        patch.object(open_file_mod.subprocess, "Popen", return_value=proc) as popen,
        patch.object(open_file_mod.time, "sleep", return_value=None),
    ):
        ok, msg = open_path(pdf, preferred_viewer="papers")

    assert ok is True
    assert "papers" in msg.lower()
    called = popen.call_args[0][0]
    assert "org.gnome.Papers" in called
    assert called[-1] == str(pdf.resolve())
    assert not any(a.startswith("file://") for a in called)


def test_open_path_firefox_handoff_success(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    proc = MagicMock()
    proc.poll.side_effect = [None, 0]

    with (
        patch.dict("os.environ", {"DISPLAY": ":0"}, clear=False),
        patch.object(open_file_mod, "_candidates", return_value=[["/usr/bin/firefox"]]),
        patch.object(open_file_mod.subprocess, "Popen", return_value=proc) as popen,
        patch.object(open_file_mod, "_BROWSER_HANDOFF_WAIT_S", 0.2),
        patch.object(open_file_mod, "_BROWSER_OPEN_GAP_S", 0.0),
        patch.object(open_file_mod, "_LAST_BROWSER_OPEN_AT", 0.0),
    ):
        ok, msg = open_path(pdf, preferred_viewer="firefox")

    assert ok is True
    assert "firefox" in msg.lower()
    called = popen.call_args[0][0]
    assert "--new-tab" in called
    assert called[-1].startswith("file://")


def test_open_path_firefox_nonzero_tries_next(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    bad = MagicMock()
    bad.poll.return_value = 1
    good = MagicMock()
    good.poll.return_value = None

    with (
        patch.dict("os.environ", {"DISPLAY": ":0"}, clear=False),
        patch.object(
            open_file_mod,
            "_candidates",
            return_value=[["/usr/bin/firefox"], ["/usr/bin/evince"]],
        ),
        patch.object(open_file_mod.subprocess, "Popen", side_effect=[bad, good]) as popen,
        patch.object(open_file_mod, "_BROWSER_HANDOFF_WAIT_S", 0.05),
        patch.object(open_file_mod, "_BROWSER_OPEN_GAP_S", 0.0),
        patch.object(open_file_mod, "_LAST_BROWSER_OPEN_AT", 0.0),
        patch.object(open_file_mod.time, "sleep", return_value=None),
    ):
        ok, msg = open_path(pdf)

    assert ok is True
    assert "evince" in msg.lower()
    assert popen.call_count == 2


def test_open_path_serializes_browser_gap(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    proc = MagicMock()
    proc.poll.return_value = 0
    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    with (
        patch.dict("os.environ", {"DISPLAY": ":0"}, clear=False),
        patch.object(open_file_mod, "_candidates", return_value=[["/usr/bin/firefox"]]),
        patch.object(open_file_mod.subprocess, "Popen", return_value=proc),
        patch.object(open_file_mod, "_BROWSER_HANDOFF_WAIT_S", 0.0),
        patch.object(open_file_mod, "_BROWSER_OPEN_GAP_S", 0.5),
        patch.object(open_file_mod, "_LAST_BROWSER_OPEN_AT", open_file_mod.time.monotonic()),
        patch.object(open_file_mod.time, "sleep", side_effect=fake_sleep),
    ):
        ok, _ = open_path(pdf, preferred_viewer="firefox")

    assert ok is True
    assert any(s > 0 for s in sleeps)
