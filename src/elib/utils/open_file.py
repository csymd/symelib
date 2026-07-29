"""
Open local files (PDFs) with a configurable or OS default application.

Preferred order on Linux
------------------------
1. Config / ``ELIB_PDF_VIEWER`` (aliases: ``papers``, ``firefox``, …)
2. **GNOME Papers** (Fedora “Document Viewer”, often Flatpak ``org.gnome.Papers``)
3. Other native PDF apps (evince, okular, zathura, …)
4. Firefox (toolbox fallback; serialized remote handoff)
5. xdg-open / host-spawn

Toolbox / Silverblue: host Papers may only be reachable as::

  pdf_viewer: papers
  # or:  flatpak run org.gnome.Papers

Firefox note: each ``firefox … URL`` is a short-lived remote client. We serialize
browser opens and use ``--new-tab`` to avoid queue/burst races.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import quote

# Serialize GUI opens so Firefox remote clients never race each other.
_OPEN_LOCK = threading.Lock()
_LAST_BROWSER_OPEN_AT = 0.0
# Minimum gap between browser remote opens (seconds).
_BROWSER_OPEN_GAP_S = 0.35
# How long to wait for a Firefox client to finish remote handoff (seconds).
_BROWSER_HANDOFF_WAIT_S = 1.5

# Cached Papers argv (False = not probed yet).
_PAPERS_ARGV: list[str] | None | bool = False

# User-facing aliases → resolved at open time.
_PAPERS_ALIASES = frozenset(
    {
        "papers",
        "document-viewer",
        "document_viewer",
        "documentviewer",
        "gnome-papers",
        "gnome_papers",
        "org.gnome.papers",
    }
)


def _which(cmd: str) -> str | None:
    if not cmd:
        return None
    p = Path(cmd).expanduser()
    if p.is_file() and os.access(p, os.X_OK):
        return str(p)
    return shutil.which(cmd)


def _file_url(path: Path) -> str:
    """file:// URL safe for browsers (absolute path)."""
    return "file://" + quote(str(path.resolve()), safe="/")


def _is_browser(cmd: str) -> bool:
    name = Path(cmd).name.lower()
    return any(b in name for b in ("firefox", "chrome", "chromium", "brave", "edge", "opera"))


def _is_firefox(cmd: str) -> bool:
    return "firefox" in Path(cmd).name.lower()


def _viewer_label(argv: list[str]) -> str:
    """Short name for status messages."""
    joined = " ".join(argv).lower()
    if "org.gnome.papers" in joined or Path(argv[0]).name.lower() in {
        "papers",
        "org.gnome.papers",
    }:
        return "papers"
    if _is_firefox(argv[0]):
        return "firefox"
    return Path(argv[0]).name


def papers_argv(*, refresh: bool = False) -> list[str] | None:
    """
    Best launch argv for GNOME Papers (Document Viewer), or None if missing.

    Order: native ``papers`` → Flatpak export wrapper → ``flatpak run org.gnome.Papers``.
    """
    global _PAPERS_ARGV
    if not refresh and _PAPERS_ARGV is not False:
        return _PAPERS_ARGV  # type: ignore[return-value]

    found: list[str] | None = None

    native = _which("papers")
    if native:
        found = [native]
    else:
        for candidate in (
            Path("/var/lib/flatpak/exports/bin/org.gnome.Papers"),
            Path.home() / ".local/share/flatpak/exports/bin/org.gnome.Papers",
        ):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                found = [str(candidate)]
                break

        if found is None:
            flatpak = _which("flatpak")
            if flatpak:
                try:
                    r = subprocess.run(
                        [flatpak, "info", "--show-ref", "org.gnome.Papers"],
                        capture_output=True,
                        timeout=3,
                        check=False,
                    )
                    if r.returncode == 0:
                        found = [flatpak, "run", "org.gnome.Papers"]
                except (OSError, subprocess.TimeoutExpired):
                    pass

    _PAPERS_ARGV = found
    return found


def recommend_pdf_viewer() -> str:
    """
    Default config value for setup: prefer Papers, else firefox, else empty auto.
    """
    if papers_argv():
        return "papers"
    if _which("firefox"):
        return "firefox"
    return ""


def _resolve_viewer_spec(spec: str) -> list[str] | None:
    """Turn a config/env viewer string into an argv prefix (no file path)."""
    s = spec.strip()
    if not s:
        return None

    low = s.lower()
    if low in _PAPERS_ALIASES:
        return papers_argv()

    parts = s.split()
    # "flatpak run org.gnome.Papers" etc.
    if len(parts) >= 3 and parts[0] == "flatpak" and parts[1] == "run":
        flatpak = _which("flatpak")
        if flatpak:
            return [flatpak, *parts[1:]]
        return None

    if parts[0].lower() in _PAPERS_ALIASES:
        return papers_argv()

    path = _which(parts[0])
    if not path:
        return None
    return [path, *parts[1:]]


def _candidates(preferred: str | None = None) -> list[list[str]]:
    """Return argv prefixes (without the path argument) to try in order."""
    out: list[list[str]] = []
    seen: set[str] = set()

    def add(argv: list[str] | None) -> None:
        if not argv:
            return
        key = " ".join(argv)
        if key not in seen:
            seen.add(key)
            out.append(argv)

    def add_viewer(binary: str, extra: list[str] | None = None) -> None:
        path = _which(binary)
        if not path:
            return
        add([path, *(extra or [])])

    # 1) Explicit preference (config / caller)
    if preferred:
        add(_resolve_viewer_spec(preferred))

    # 2) Env override (if different string)
    env = os.environ.get("ELIB_PDF_VIEWER", "").strip()
    if env and env != (preferred or "").strip():
        add(_resolve_viewer_spec(env))

    if sys.platform == "darwin":
        add(["open"])
        return out

    if sys.platform.startswith("linux"):
        # 3) GNOME Papers / Document Viewer (before browsers)
        add(papers_argv())

        # Native PDF readers
        for name in (
            "evince",
            "papers",
            "okular",
            "zathura",
            "mupdf",
            "mupdf-gl",
        ):
            add_viewer(name)

        # Desktop openers (use host MIME default — often Papers)
        if not preferred and not env:
            add_viewer("xdg-open")
            gio = _which("gio")
            if gio:
                add([gio, "open"])

        # Browser fallback (toolbox)
        for name in (
            "firefox",
            "google-chrome",
            "chromium-browser",
            "chromium",
        ):
            add_viewer(name)

        add_viewer("xdg-open")
        gio = _which("gio")
        if gio:
            add([gio, "open"])

        for host_cmd in (
            ["flatpak-spawn", "--host", "xdg-open"],
            ["host-spawn", "xdg-open"],
        ):
            if _which(host_cmd[0]):
                add(host_cmd)

    return out


def _launch_env() -> dict[str, str]:
    """Environment for GUI apps (keep DISPLAY / WAYLAND / DBUS from parent)."""
    env = os.environ.copy()
    for key in (
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "XAUTHORITY",
        "DBUS_SESSION_BUS_ADDRESS",
        "XDG_RUNTIME_DIR",
    ):
        if key not in env and key in os.environ:
            env[key] = os.environ[key]
    return env


def _build_cmd(argv: list[str], path: Path) -> list[str]:
    """Build full argv for a viewer candidate + file path."""
    binary = argv[0]
    # Browsers prefer file://; Papers/evince/etc. want a filesystem path.
    target = _file_url(path) if _is_browser(binary) else str(path)
    cmd = list(argv)

    if _is_firefox(binary):
        cleaned = [cmd[0]]
        for part in cmd[1:]:
            low = part.lower()
            if low in ("--new-window", "-new-window", "--new-tab", "-new-tab"):
                continue
            cleaned.append(part)
        return [cleaned[0], "--new-tab", *cleaned[1:], target]

    return [*cmd, target]


def _wait_browser_handoff(proc: subprocess.Popen[bytes], *, wait_s: float) -> int | None:
    """
    Poll a short-lived browser client.

    Returns exit code if the process exited within wait_s, else None (still
    running — usually means this is the main browser cold-start).
    """
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        ret = proc.poll()
        if ret is not None:
            return ret
        time.sleep(0.05)
    return proc.poll()


def open_path(
    path: str | Path,
    *,
    preferred_viewer: str | None = None,
) -> tuple[bool, str]:
    """
    Open a file with the best available viewer.

    Returns (ok, message). On failure, message lists what was tried.

    Opens are serialized so Firefox remote clients cannot race.
    """
    p = Path(path).expanduser()
    try:
        p = p.resolve(strict=True)
    except FileNotFoundError:
        return False, f"File not found: {path}"
    if not p.is_file():
        return False, f"Not a file: {p}"

    if sys.platform == "win32":
        try:
            os.startfile(str(p))  # type: ignore[attr-defined]
            return True, f"Opened {p.name}"
        except OSError as e:
            return False, f"Could not open: {e}"

    if sys.platform == "darwin":
        try:
            subprocess.Popen(
                ["open", str(p)],
                env=_launch_env(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True, f"Opened {p.name} (open)"
        except OSError as e:
            return False, f"Could not open: {e}"

    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return (
            False,
            "No DISPLAY/WAYLAND_DISPLAY — cannot open a GUI PDF viewer from this shell. "
            "Run elib tui from a graphical session (or set DISPLAY).",
        )

    errors: list[str] = []
    cands = _candidates(preferred_viewer)
    if not cands:
        return (
            False,
            "No PDF viewer found. Install GNOME Papers (Document Viewer) or set "
            "pdf_viewer: papers / firefox in config.",
        )

    with _OPEN_LOCK:
        global _LAST_BROWSER_OPEN_AT

        for argv in cands:
            binary = argv[0]
            cmd = _build_cmd(argv, p)
            browser = _is_browser(binary)
            label = _viewer_label(argv)

            if browser and _LAST_BROWSER_OPEN_AT > 0:
                gap = time.monotonic() - _LAST_BROWSER_OPEN_AT
                if gap < _BROWSER_OPEN_GAP_S:
                    time.sleep(_BROWSER_OPEN_GAP_S - gap)

            try:
                proc = subprocess.Popen(
                    cmd,
                    env=_launch_env(),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError as e:
                errors.append(f"{label}: {e}")
                continue

            if browser:
                ret = _wait_browser_handoff(proc, wait_s=_BROWSER_HANDOFF_WAIT_S)
                _LAST_BROWSER_OPEN_AT = time.monotonic()
                if ret is not None and ret != 0:
                    errors.append(f"{label} exited {ret}")
                    continue
                return True, f"Opened {p.name} via {label}"

            # Native / flatpak app: process usually stays up. Immediate non-zero = fail.
            time.sleep(0.15)
            ret = proc.poll()
            if ret is not None and ret != 0:
                errors.append(f"{label} exited {ret}")
                continue
            return True, f"Opened {p.name} via {label}"

    hint = (
        f"Could not open PDF (DISPLAY={os.environ.get('DISPLAY', '?')}). "
        "Try pdf_viewer: papers (GNOME Document Viewer) or firefox. "
        f"Path was: {p}"
    )
    if errors:
        return False, hint + " Tried: " + "; ".join(errors[:4])
    return False, hint
