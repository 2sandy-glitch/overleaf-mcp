"""Picks the integration for a project's ``backend`` setting.

To add a new way of reaching Overleaf (e.g. the web-session API), add a folder
or file here that implements integrations/backend.py:Backend and one branch below.
"""

from pathlib import Path

from agent.errors import BackendError
from integrations.backend import Backend
from integrations.git.client import GitBackend
from integrations.overleaf.git_bridge import overleaf_git_backend
from src import data_dir


def build_backend(pc) -> Backend:
    if pc.backend == "overleaf-git":
        workdir = data_dir() / "workspaces" / pc.key
        return overleaf_git_backend(workdir, pc.project_id, pc.token, pc.git_host, pc.branch)
    if pc.backend == "git":
        workdir = data_dir() / "workspaces" / pc.key
        return GitBackend(workdir, remote_url=pc.remote_url, token=pc.token, branch=pc.branch)
    if pc.backend == "local":
        return GitBackend(Path(pc.path))
    raise BackendError(f"Unknown backend '{pc.backend}'")
