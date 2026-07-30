"""
elib setup — interactive NCBI credentials + library paths.

Writes:
  - $ELIB_HOME/config.yaml (default ~/elibrary/config.yaml)  [not in git]
  - ~/.config/elib/env  (export ELIB_NCBI_EMAIL / ELIB_NCBI_API_KEY)
  - Creates cart/, library/, texts/, data/, exports/, tmp/ under $ELIB_HOME
"""

from __future__ import annotations

from getpass import getpass
import os
from pathlib import Path
import stat
import subprocess

import typer
import yaml

from symworx_elibrary.utils.config import ELIB_HOME_SUBDIRS, get_elib_home


def setup(
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Use env vars / flags only; do not prompt.",
    ),
    email: str | None = typer.Option(None, "--email", "-e", help="NCBI contact email"),
    api_key: str | None = typer.Option(None, "--api-key", "-k", help="NCBI API key"),
    pdf_viewer: str | None = typer.Option(None, "--pdf-viewer", help="PDF viewer command"),
    elib_home: Path | None = typer.Option(
        None, "--elib-home", help="Library root (default: ~/elibrary)"
    ),
    write_shell_rc: bool = typer.Option(
        True,
        "--shell-rc/--no-shell-rc",
        help="Append source line to ~/.bashrc or ~/.zshrc",
    ),
    install_cli: bool = typer.Option(
        False,
        "--install-cli",
        help="Run `uv tool install --editable .` after writing config",
    ),
):
    """
    Interactive setup for NCBI email/API key and library paths.

    Also available as:  bash scripts/setup.sh
    """
    home = Path(elib_home).expanduser() if elib_home else get_elib_home()
    config_path = home / "config.yaml"
    config_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "elib"
    env_path = config_dir / "env"

    typer.echo("elib setup")
    typer.echo(f"  Library:  {home}")
    typer.echo(f"  Config:   {config_path}")
    typer.echo(f"  Env file: {env_path}")
    typer.echo("")

    existing: dict = {}
    if config_path.exists():
        existing = yaml.safe_load(config_path.read_text()) or {}

    # Resolve email
    resolved_email = email or os.environ.get("ELIB_NCBI_EMAIL") or existing.get("ncbi_email") or ""
    resolved_key = (
        api_key or os.environ.get("ELIB_NCBI_API_KEY") or existing.get("ncbi_api_key") or None
    )
    if resolved_key in ("", "null", None):
        resolved_key = None
    from symworx_elibrary.utils.open_file import recommend_pdf_viewer

    resolved_viewer = (
        pdf_viewer
        or os.environ.get("ELIB_PDF_VIEWER")
        or existing.get("pdf_viewer")
        or recommend_pdf_viewer()
        or "papers"
    )

    if not non_interactive:
        typer.echo("NCBI requires a contact email for E-utilities.")
        typer.echo("API key (optional) raises rate limits ~3 → ~10 req/s.")
        typer.echo("  https://www.ncbi.nlm.nih.gov/account/settings/")
        typer.echo("")
        prompt_email = typer.prompt("NCBI email", default=resolved_email or "you@example.com")
        resolved_email = prompt_email.strip()

        if resolved_key:
            keep = typer.confirm("Keep existing API key?", default=True)
            if not keep:
                entered = getpass("NCBI API key (empty to clear): ").strip()
                resolved_key = entered or None
        else:
            entered = getpass("NCBI API key (empty to skip): ").strip()
            resolved_key = entered or None

        typer.echo(
            "PDF viewer: 'papers' = GNOME Document Viewer (recommended). "
            "Also: firefox, evince, or a full command."
        )
        resolved_viewer = typer.prompt(
            "PDF viewer command", default=str(resolved_viewer or "papers")
        ).strip()

    if not resolved_email or resolved_email.endswith("example.com"):
        typer.secho(
            "Warning: NCBI expects a real contact email.",
            fg=typer.colors.YELLOW,
        )

    # Library layout: cart, library, texts, data, exports, tmp
    for sub in ELIB_HOME_SUBDIRS:
        (home / sub).mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    typer.secho(
        f"Directories: {', '.join(ELIB_HOME_SUBDIRS)} under {home}",
        fg=typer.colors.GREEN,
    )

    # config.yaml merge — never put org-specific bucket defaults
    data = dict(existing)
    data["ncbi_email"] = resolved_email
    if resolved_key:
        data["ncbi_api_key"] = resolved_key
    elif "ncbi_api_key" in data and not resolved_key:
        data["ncbi_api_key"] = None
    data["database_path"] = str(data.get("database_path") or home / "data" / "elib.db")
    data["target_directory"] = str(data.get("target_directory") or home / "library")
    data["cart_directory"] = str(data.get("cart_directory") or home / "cart")
    data["texts_directory"] = str(data.get("texts_directory") or home / "texts")
    data["exports_directory"] = str(data.get("exports_directory") or home / "exports")
    data["temp_directory"] = str(data.get("temp_directory") or home / "tmp")
    if resolved_viewer:
        data["pdf_viewer"] = resolved_viewer
    # Drop empty S3 bucket defaults if present with no override intent
    if data.get("s3_bucket") in (None, ""):
        data.pop("s3_bucket", None)
    if not data.get("rclone_remote"):
        data.pop("rclone_remote", None)

    config_path.write_text(
        yaml.safe_dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    typer.secho(f"Wrote {config_path}", fg=typer.colors.GREEN)

    # env file
    lines = [
        "# elib environment — generated by elib setup",
        f"# Source:  source {env_path}",
        "",
        f'export ELIB_HOME="{home}"',
        f'export ELIB_CONFIG="{config_path}"',
        f'export ELIB_NCBI_EMAIL="{resolved_email}"',
        f'export ELIB_EXPORTS_DIRECTORY="{home / "exports"}"',
        f'export ELIB_TEMP_DIRECTORY="{home / "tmp"}"',
    ]
    if resolved_key:
        lines.append(f'export ELIB_NCBI_API_KEY="{resolved_key}"')
        lines.append(f'export NCBI_API_KEY="{resolved_key}"')
    else:
        lines.append("# export ELIB_NCBI_API_KEY=")
    if resolved_viewer:
        lines.append(f'export ELIB_PDF_VIEWER="{resolved_viewer}"')
    lines += [
        "",
        'case ":$PATH:" in',
        '  *":$HOME/.local/bin:"*) ;;',
        '  *) export PATH="$HOME/.local/bin:$PATH" ;;',
        "esac",
        "",
    ]
    env_path.write_text("\n".join(lines), encoding="utf-8")
    env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600
    typer.secho(f"Wrote {env_path} (mode 600)", fg=typer.colors.GREEN)

    # shell rc
    if write_shell_rc and not non_interactive:
        shell = os.environ.get("SHELL", "")
        rc = Path.home() / (".zshrc" if "zsh" in shell else ".bashrc")
        if typer.confirm(f"Add source line to {rc}?", default=True):
            marker = str(env_path)
            content = rc.read_text() if rc.exists() else ""
            if marker not in content:
                with rc.open("a", encoding="utf-8") as f:
                    f.write("\n# elib (NCBI email / API key / PATH)\n")
                    f.write(f'[ -f "{env_path}" ] && source "{env_path}"  # elib\n')
                typer.secho(f"Updated {rc}", fg=typer.colors.GREEN)
            else:
                typer.echo(f"Already sourcing env from {rc}")

    if install_cli:
        repo = Path(__file__).resolve().parents[3]
        try:
            subprocess.run(
                ["uv", "tool", "install", "--force", "--editable", str(repo)],
                check=True,
            )
            typer.secho("Installed elib CLI via uv tool", fg=typer.colors.GREEN)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            typer.secho(f"CLI install failed: {e}", fg=typer.colors.RED, err=True)

    typer.echo("")
    typer.secho(
        "IMPORTANT: env vars are written to a file — they are NOT injected into "
        "this shell automatically.",
        fg=typer.colors.YELLOW,
        bold=True,
    )
    typer.echo("Load them now:")
    typer.echo(f"  {typer.style('source ' + str(env_path), bold=True)}")
    typer.echo("Or open a new terminal (if your ~/.bashrc sources that file).")
    typer.echo("")
    typer.echo("Layout:")
    typer.echo(f"  cart/ library/ texts/ data/ exports/ tmp/  →  {home}")
    typer.echo("")
    typer.echo("Verify:")
    typer.echo("  echo $ELIB_NCBI_EMAIL")
    typer.echo("  echo ${ELIB_NCBI_API_KEY:+set}   # prints 'set' if key is loaded")
    typer.echo("  elib stats")
    if resolved_key:
        typer.echo("  elib process --limit 50")
    else:
        typer.echo("  elib process --limit 50 --delay 0.8")
