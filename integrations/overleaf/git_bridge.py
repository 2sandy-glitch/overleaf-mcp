"""Overleaf's official Git bridge: <git_host>/<project_id>, user "git", token as password.

Needs Overleaf's Git integration (a paid-plan feature on overleaf.com).
If a web session cookie is also configured, compiling on Overleaf works too.
"""

from pathlib import Path

from integrations.git.client import GitBackend
from integrations.overleaf.remote_compile import compile_on_overleaf, unpushed_note


class OverleafGitBackend(GitBackend):
    def __init__(self, workdir: Path, project_id: str, token: str, git_host: str, branch: str = "", client_factory=None, main_file: str = "main.tex"):
        url = f"{git_host.rstrip('/')}/{project_id}"
        super().__init__(workdir, remote_url=url, token=token, username="git", branch=branch, label="overleaf-git")
        self.project_id = project_id
        self.main_file = main_file
        self._client_factory = client_factory
        self.can_remote_compile = client_factory is not None

    def remote_compile(self, main_file: str | None, out_dir: Path) -> dict:
        self.ensure_ready()
        client = self._client_factory()
        try:
            result = compile_on_overleaf(client, self.project_id, main_file or self.main_file, out_dir)
        finally:
            client.close()
        return {**result, "note": unpushed_note(self.status())}


def overleaf_git_backend(workdir: Path, project_id: str, token: str, git_host: str, branch: str = "", client_factory=None, main_file: str = "main.tex") -> OverleafGitBackend:
    return OverleafGitBackend(workdir, project_id, token, git_host, branch, client_factory, main_file)
