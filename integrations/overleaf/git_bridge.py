"""Overleaf's official Git bridge: <git_host>/<project_id>, user "git", token as password.

Needs Overleaf's Git integration (a paid-plan feature on overleaf.com).
A future web-session integration (works on free plans) goes next to this file.
"""

from pathlib import Path

from integrations.git.client import GitBackend


def overleaf_git_backend(workdir: Path, project_id: str, token: str, git_host: str, branch: str = "") -> GitBackend:
    url = f"{git_host.rstrip('/')}/{project_id}"
    return GitBackend(workdir, remote_url=url, token=token, username="git", branch=branch, label="overleaf-git")
