"""
tests/unit/utils/test_config.py
"""

from pathlib import Path

from elib.utils.config import Config, default_config_candidates, get_elib_home


def test_get_elib_home_default(monkeypatch):
    monkeypatch.delenv("ELIB_HOME", raising=False)
    assert get_elib_home() == Path.home() / "elibrary"


def test_get_elib_home_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ELIB_HOME", str(tmp_path / "lib"))
    assert get_elib_home() == (tmp_path / "lib").resolve()


def test_load_from_explicit_path(tmp_path, monkeypatch):
    monkeypatch.delenv("ELIB_CONFIG", raising=False)
    monkeypatch.delenv("ELIB_DATABASE_PATH", raising=False)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "ncbi_email: test@example.com\n"
        f"database_path: {tmp_path / 'data' / 'elib.db'}\n"
        f"target_directory: {tmp_path / 'library'}\n"
        f"cart_directory: {tmp_path / 'cart'}\n"
    )
    cfg = Config.load(cfg_file)
    assert cfg.ncbi_email == "test@example.com"
    assert cfg.database_path == (tmp_path / "data" / "elib.db").resolve()
    assert cfg.target_directory == (tmp_path / "library").resolve()
    assert cfg.database_path.parent.exists()
    assert cfg.target_directory.exists()


def test_expand_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    # re-import not needed; expanduser uses HOME
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(
        "ncbi_email: a@b.c\n"
        "database_path: ~/elibrary/data/elib.db\n"
        "target_directory: ~/elibrary/library\n"
    )
    cfg = Config.load(cfg_file)
    assert str(cfg.database_path).startswith(str(tmp_path))
    assert cfg.database_path.name == "elib.db"


def test_candidates_include_elibrary(monkeypatch):
    monkeypatch.delenv("ELIB_CONFIG", raising=False)
    cands = default_config_candidates()
    assert any(p.name == "config.yaml" for p in cands)
