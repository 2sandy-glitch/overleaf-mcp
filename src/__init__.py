"""Shared helpers: app settings (config.json) and where things live on disk."""

import json
import os
from functools import lru_cache
from pathlib import Path

VERSION = "0.2.0"
ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def _settings() -> dict:
    return json.loads((ROOT / "config.json").read_text())


def get_config(section: str) -> dict:
    """One section of config.json (non-secret app settings)."""
    return _settings()[section]


def _xdg(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / fallback)


def projects_file() -> Path:
    """The user's project list with tokens: OVERLEAF_MCP_CONFIG or ~/.config/overleaf-mcp/projects.json."""
    explicit = os.environ.get("OVERLEAF_MCP_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    return _xdg("XDG_CONFIG_HOME", ".config") / "overleaf-mcp" / "projects.json"


def data_dir() -> Path:
    """Working copies and build output: OVERLEAF_MCP_HOME or ~/.local/share/overleaf-mcp."""
    explicit = os.environ.get("OVERLEAF_MCP_HOME")
    if explicit:
        return Path(explicit).expanduser()
    return _xdg("XDG_DATA_HOME", ".local/share") / "overleaf-mcp"


def prompt_dirs() -> list[Path]:
    """Built-in prompts first, then the user's own (user ones win on a name clash)."""
    return [ROOT / "prompts", projects_file().parent / "recipes"]
