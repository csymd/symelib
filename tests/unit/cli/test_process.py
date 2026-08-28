"""
tests/unit/cli/test_process.py — inbox sequence for elib process
"""

from pathlib import Path

from symworx_elibrary.cli.process import ProcessFrom, resolve_process_sources
from symworx_elibrary.utils.config import Config


def _cfg(tmp_path: Path, *, tmp_name: str = "tmp", cart_name: str = "cart") -> Config:
    return Config(
        ncbi_email="test@example.com",
        database_path=tmp_path / "data" / "elib.db",
        target_directory=tmp_path / "library",
        cart_directory=tmp_path / cart_name,
        temp_directory=tmp_path / tmp_name,
        exports_directory=tmp_path / "exports",
    )


def test_resolve_all_is_tmp_then_cart(tmp_path: Path):
    cfg = _cfg(tmp_path)
    sources = resolve_process_sources(config=cfg, from_inbox=ProcessFrom.all)
    assert sources == [cfg.temp_directory, cfg.cart_directory]


def test_resolve_tmp_or_cart_only(tmp_path: Path):
    cfg = _cfg(tmp_path)
    assert resolve_process_sources(config=cfg, from_inbox=ProcessFrom.tmp) == [cfg.temp_directory]
    assert resolve_process_sources(config=cfg, from_inbox=ProcessFrom.cart) == [cfg.cart_directory]


def test_explicit_path_wins_over_from(tmp_path: Path):
    cfg = _cfg(tmp_path)
    other = tmp_path / "other-pdfs"
    sources = resolve_process_sources(
        config=cfg,
        source_dir=other,
        from_inbox=ProcessFrom.tmp,
    )
    assert sources == [other]


def test_resolve_dedupes_when_tmp_equals_cart(tmp_path: Path):
    cfg = _cfg(tmp_path, tmp_name="inbox", cart_name="inbox")
    sources = resolve_process_sources(config=cfg, from_inbox=ProcessFrom.all)
    assert sources == [cfg.temp_directory]
