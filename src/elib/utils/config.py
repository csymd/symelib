"""
src/elib/utils/config.py

Configuration loading for elib.

Search order for config.yaml:
  1. ELIB_CONFIG env var (file path)
  2. ./config.yaml (current working directory; gitignored)
  3. $ELIB_HOME/config.yaml  (default ELIB_HOME=~/elibrary)
  4. ~/.config/elib/config.yaml
  5. Built-in defaults

Never commit a filled-in config.yaml. Use config.example.yaml as the template.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
import yaml

# ========================================================= #
# Application Configuration Model                           #
# ========================================================= #

# Default library root for papers + SQLite (outside the git repo)
DEFAULT_ELIB_HOME = Path.home() / "elibrary"

# Subdirs created under $ELIB_HOME by setup / ensure_dirs
ELIB_HOME_SUBDIRS = (
    "cart",
    "library",
    "texts",
    "data",
    "exports",
    "tmp",
)


def get_elib_home() -> Path:
    """Root of the local paper tree (user data; not part of the git repo)."""
    raw = os.environ.get("ELIB_HOME", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_ELIB_HOME


def default_config_candidates() -> list[Path]:
    """Ordered list of config file locations to try."""
    candidates: list[Path] = []
    env_cfg = os.environ.get("ELIB_CONFIG", "").strip()
    if env_cfg:
        candidates.append(Path(env_cfg).expanduser())
    candidates.append(Path("config.yaml"))  # cwd (gitignored if in repo)
    candidates.append(get_elib_home() / "config.yaml")
    candidates.append(Path.home() / ".config" / "elib" / "config.yaml")
    return candidates


class Config(BaseModel):
    """Application configuration"""

    ncbi_email: str = "your.email@example.com"
    ncbi_api_key: str | None = None
    # SQLite metadata DB
    database_path: Path = Field(default_factory=lambda: get_elib_home() / "data" / "elib.db")
    # Processed / renamed PDFs
    target_directory: Path = Field(default_factory=lambda: get_elib_home() / "library")
    # Raw inbox of unprocessed PDFs
    cart_directory: Path = Field(default_factory=lambda: get_elib_home() / "cart")
    # Optional: books / non-paper texts
    texts_directory: Path = Field(default_factory=lambda: get_elib_home() / "texts")
    # BibTeX / list exports
    exports_directory: Path = Field(default_factory=lambda: get_elib_home() / "exports")
    # Scratch / temporary working files
    temp_directory: Path = Field(default_factory=lambda: get_elib_home() / "tmp")
    # Optional AWS / rclone markers (informational only; no default bucket)
    s3_bucket: str | None = None
    rclone_remote: str | None = None
    # PDF viewer: "papers", "firefox", or full command. Empty → auto-detect.
    pdf_viewer: str | None = None

    @field_validator(
        "database_path",
        "target_directory",
        "cart_directory",
        "texts_directory",
        "exports_directory",
        "temp_directory",
        mode="before",
    )
    @classmethod
    def _expand_path(cls, v):
        if v is None or v == "":
            return v
        p = Path(v).expanduser()
        return p

    def ensure_dirs(self) -> None:
        """Create configured data directories if missing."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        for path in (
            self.target_directory,
            self.cart_directory,
            self.texts_directory,
            self.exports_directory,
            self.temp_directory,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls, config_path: Path | None = None) -> Config:
        """
        Load configuration from YAML.

        If config_path is given, use it. Otherwise walk default_config_candidates().
        Paths in the YAML may use ~ ; relative paths are resolved against the
        config file's parent directory (or cwd if no file was found).
        """
        path: Path | None = None
        data: dict = {}

        if config_path is not None:
            path = Path(config_path).expanduser()
            if path.exists():
                with open(path) as f:
                    data = yaml.safe_load(f) or {}
            else:
                raise FileNotFoundError(f"Config not found: {path}")
        else:
            for candidate in default_config_candidates():
                if candidate.exists():
                    path = candidate
                    with open(candidate) as f:
                        data = yaml.safe_load(f) or {}
                    break

        # Env overrides (optional)
        if os.environ.get("ELIB_NCBI_EMAIL"):
            data["ncbi_email"] = os.environ["ELIB_NCBI_EMAIL"]
        if os.environ.get("ELIB_NCBI_API_KEY"):
            data["ncbi_api_key"] = os.environ["ELIB_NCBI_API_KEY"]
        if os.environ.get("ELIB_DATABASE_PATH"):
            data["database_path"] = os.environ["ELIB_DATABASE_PATH"]
        if os.environ.get("ELIB_TARGET_DIRECTORY"):
            data["target_directory"] = os.environ["ELIB_TARGET_DIRECTORY"]
        if os.environ.get("ELIB_EXPORTS_DIRECTORY"):
            data["exports_directory"] = os.environ["ELIB_EXPORTS_DIRECTORY"]
        if os.environ.get("ELIB_TEMP_DIRECTORY"):
            data["temp_directory"] = os.environ["ELIB_TEMP_DIRECTORY"]
        if os.environ.get("ELIB_PDF_VIEWER"):
            data["pdf_viewer"] = os.environ["ELIB_PDF_VIEWER"]

        cfg = cls(**data) if data else cls()

        # Resolve relative paths against config file directory or elib home
        base = path.parent.resolve() if path is not None else get_elib_home()
        for field in (
            "database_path",
            "target_directory",
            "cart_directory",
            "texts_directory",
            "exports_directory",
            "temp_directory",
        ):
            p: Path = getattr(cfg, field)
            if not p.is_absolute():
                setattr(cfg, field, (base / p).resolve())
            else:
                setattr(cfg, field, p.expanduser().resolve())

        cfg.ensure_dirs()
        return cfg

    def save(self, config_path: Path | None = None) -> None:
        """Save configuration to YAML file (never commit secrets)."""
        path = Path(config_path).expanduser() if config_path else get_elib_home() / "config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ncbi_email": self.ncbi_email,
            "ncbi_api_key": self.ncbi_api_key,
            "database_path": str(self.database_path),
            "target_directory": str(self.target_directory),
            "cart_directory": str(self.cart_directory),
            "texts_directory": str(self.texts_directory),
            "exports_directory": str(self.exports_directory),
            "temp_directory": str(self.temp_directory),
            "pdf_viewer": self.pdf_viewer,
        }
        if self.s3_bucket:
            payload["s3_bucket"] = self.s3_bucket
        if self.rclone_remote:
            payload["rclone_remote"] = self.rclone_remote
        with open(path, "w") as f:
            yaml.safe_dump(payload, f, default_flow_style=False, sort_keys=False)
