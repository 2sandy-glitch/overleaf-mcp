"""One Workspace per configured project, created on first use, plus the
`run` helper every tool goes through (project lock + error mapping)."""

from mcp.server.mcpserver.exceptions import ToolError

from agent.errors import OverleafMCPError
from src.projects import load_projects
from src.workspace import Workspace

_spaces: dict[str, Workspace] = {}


def workspace(project: str | None) -> Workspace:
    pc = load_projects().get(project)
    ws = _spaces.get(pc.key)
    if ws is None or ws.config != pc:
        ws = Workspace(pc)
        _spaces[pc.key] = ws
    return ws


def run(project: str | None, fn):
    """Run fn(workspace) under that project's lock; our errors become tool errors."""
    try:
        ws = workspace(project)
        with ws.lock:
            return fn(ws)
    except OverleafMCPError as exc:
        raise ToolError(str(exc)) from exc


def reset() -> None:
    """Forget cached workspaces (tests, or after editing projects.json)."""
    _spaces.clear()
