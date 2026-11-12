"""Project & sync tools: which projects exist, and moving edits to/from Overleaf."""

from mcp.server.mcpserver.exceptions import ToolError

from agent.errors import ConfigError, OverleafMCPError
from agent.registry import run
from integrations.overleaf.web_client import OverleafWebClient
from src import get_config, projects_file
from src.projects import load_projects, shared_cookie


def list_projects() -> dict:
    """List configured projects (no secrets) and which one is the default."""
    try:
        p = load_projects()
    except ConfigError as exc:
        raise ToolError(str(exc)) from exc
    return {
        "default": p.default,
        "config_file": str(projects_file()),
        "projects": [pc.public() for pc in p.items.values()],
    }


def list_overleaf_projects(query: str = "") -> list[dict]:
    """List the projects in the signed-in Overleaf account (needs ./entry.sh login).
    Use it to find a project_id to add to projects.json. `query` filters by name."""
    try:
        client = OverleafWebClient(get_config("overleaf")["web_url"], shared_cookie())
        try:
            projects = client.list_projects()
        finally:
            client.close()
    except OverleafMCPError as exc:
        raise ToolError(str(exc)) from exc
    q = query.lower().strip()
    return [p for p in projects if not p["trashed"] and (not q or q in (p["name"] or "").lower())]


def pull(project: str | None = None) -> dict:
    """Fetch the latest version from Overleaf into the local working copy.
    Local edits are kept; if they clash with remote changes nothing is changed."""
    return run(project, lambda ws: ws.backend.pull().as_dict())


def status(project: str | None = None) -> dict:
    """Show local edits not yet pushed to Overleaf."""
    return run(project, lambda ws: {**ws.config.public(), **ws.backend.status()})


def diff(project: str | None = None, path: str | None = None) -> str:
    """Unified diff of everything that `push` would send (optionally one file)."""
    return run(project, lambda ws: ws.backend.diff(path) or "No local changes.")


def push(message: str, project: str | None = None) -> dict:
    """Publish local edits to Overleaf as one commit. Refuses, without
    overwriting, if someone changed the same lines on Overleaf meanwhile.
    Show the user the diff and get confirmation before calling this."""
    return run(project, lambda ws: ws.backend.push(message).as_dict())


def discard_changes(project: str | None = None, paths: list[str] | None = None) -> dict:
    """Throw away local edits not yet pushed (all, or only `paths`)."""
    return run(project, lambda ws: ws.backend.discard(paths).as_dict())


# (function, effect) — effect picks the MCP annotation in tools/registry.py
TOOLS = [
    (list_projects, "read"),
    (list_overleaf_projects, "remote_read"),
    (pull, "remote"),
    (status, "read"),
    (diff, "read"),
    (push, "remote"),
    (discard_changes, "destructive"),
]
