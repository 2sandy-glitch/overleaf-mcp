"""Git client: syncs a working copy with any git remote, or none.

Covers three setups with one class:
  * Overleaf's Git bridge (built by integrations/overleaf/git_bridge.py)
  * any other git remote (self-hosted Overleaf, GitHub, GitLab...)
  * a local folder with no remote at all (push = local commit)

The token is handed to git through GIT_CONFIG_* environment variables as an
HTTP header, so it never lands in .git/config, the remote URL, or the
process command line.
"""

import base64
import os
import subprocess
from pathlib import Path

from agent.errors import BackendError
from integrations.backend import Backend, SyncResult
from src import get_config


class GitBackend(Backend):
    kind = "git"

    def __init__(
        self,
        workdir: Path,
        remote_url: str = "",
        token: str = "",
        username: str = "git",
        branch: str = "",
        label: str = "",
    ):
        super().__init__(workdir)
        self.label = label or ("overleaf-git" if token else ("git" if remote_url else "local"))
        self.remote_url = remote_url
        self.branch = branch
        self._token = token
        self._username = username

    # ---- plumbing -------------------------------------------------------

    def _env(self) -> dict:
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "true"}
        if self._token:
            basic = base64.b64encode(f"{self._username}:{self._token}".encode()).decode()
            env.update(
                {
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "http.extraHeader",
                    "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
                }
            )
        return env

    def _redact(self, text: str) -> str:
        if self._token:
            text = text.replace(self._token, "***")
        return text

    def _git(self, *args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
        timeout = get_config("git")["timeout_seconds"]
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=cwd or self.workdir,
                env=self._env(),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise BackendError(f"git {args[0]} timed out after {timeout}s") from exc
        if check and proc.returncode != 0:
            detail = self._redact((proc.stderr or proc.stdout).strip())
            raise BackendError(f"git {args[0]} failed: {detail}")
        return proc

    def _current_branch(self) -> str:
        return self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    def _has_commits(self) -> bool:
        return self._git("rev-parse", "--verify", "HEAD", check=False).returncode == 0

    def _changed_files(self) -> list[str]:
        out = self._git("status", "--porcelain", "-uall").stdout
        return [line[3:] for line in out.splitlines() if line.strip()]

    def _set_identity(self) -> None:
        git_cfg = get_config("git")
        self._git("config", "user.name", git_cfg["commit_name"])
        self._git("config", "user.email", git_cfg["commit_email"])

    # ---- contract -------------------------------------------------------

    def ensure_ready(self) -> None:
        if (self.workdir / ".git").exists():
            return
        if self.remote_url:
            self.workdir.parent.mkdir(parents=True, exist_ok=True)
            self._git("clone", self.remote_url, str(self.workdir), cwd=self.workdir.parent)
        else:
            self.workdir.mkdir(parents=True, exist_ok=True)
            self._git("init", "-q")
        self._set_identity()
        if not self.remote_url and not self._has_commits():
            self._git("add", "-A")
            self._git("commit", "-q", "--allow-empty", "-m", "Baseline snapshot")

    def pull(self) -> SyncResult:
        self.ensure_ready()
        if not self.remote_url:
            return SyncResult(True, "pull", "Local project: nothing to pull.")
        before = self._git("rev-parse", "HEAD").stdout.strip()
        branch = self.branch or self._current_branch()
        proc = self._git("pull", "--rebase", "--autostash", "origin", branch, check=False)
        if proc.returncode != 0:
            conflicts = self._conflicted()
            self._git("rebase", "--abort", check=False)
            return SyncResult(
                False,
                "pull",
                "Remote changes clash with local edits; nothing was changed. "
                "Push or discard your local edits to those files first.",
                conflicts=conflicts,
            )
        after = self._git("rev-parse", "HEAD").stdout.strip()
        changed = []
        if before != after:
            changed = self._git("diff", "--name-only", before, after).stdout.split()
        msg = f"Pulled {len(changed)} changed file(s)." if changed else "Already up to date."
        return SyncResult(True, "pull", msg, changed_files=changed)

    def _conflicted(self) -> list[str]:
        out = self._git("diff", "--name-only", "--diff-filter=U", check=False).stdout
        return out.split()

    def push(self, message: str) -> SyncResult:
        self.ensure_ready()
        changed = self._changed_files()
        if changed:
            self._git("add", "-A")
            self._git("commit", "-q", "-m", message or "Update via overleaf-mcp")
        if not self.remote_url:
            if not changed:
                return SyncResult(True, "push", "No local changes to save.")
            return SyncResult(True, "push", "Saved a local snapshot (no remote).", changed_files=changed)

        branch = self.branch or self._current_branch()
        proc = self._git("pull", "--rebase", "origin", branch, check=False)
        if proc.returncode != 0:
            conflicts = self._conflicted()
            self._git("rebase", "--abort", check=False)
            return SyncResult(
                False,
                "push",
                "Someone changed the same lines on Overleaf. Nothing was pushed; your "
                "edits are kept locally as a commit. Pull, re-apply, then push again.",
                changed_files=changed,
                conflicts=conflicts,
            )
        ahead = self._git("rev-list", "--count", f"origin/{branch}..HEAD").stdout.strip()
        if ahead == "0":
            return SyncResult(True, "push", "No local changes to push.")
        return self._publish(branch, int(ahead))

    def _publish(self, branch: str, ahead: int) -> SyncResult:
        """Send the rebased local commits to the remote. Integrations that are not
        plain git (e.g. the Overleaf web session) override this step only."""
        files = self._git("diff", "--name-only", f"origin/{branch}", "HEAD").stdout.split()
        self._git("push", "origin", f"HEAD:{branch}")
        return SyncResult(True, "push", f"Pushed {ahead} commit(s) to the remote.", changed_files=files)

    def status(self) -> dict:
        self.ensure_ready()
        info = {
            "backend": self.label,
            "uncommitted_changes": self._changed_files(),
            "unpushed_commits": 0,
        }
        if self.remote_url and self._has_commits():
            branch = self.branch or self._current_branch()
            proc = self._git("rev-list", "--count", f"origin/{branch}..HEAD", check=False)
            if proc.returncode == 0:
                info["unpushed_commits"] = int(proc.stdout.strip() or 0)
        return info

    def diff(self, path: str | None = None) -> str:
        self.ensure_ready()
        # Include untracked files in the diff by marking them intent-to-add.
        self._git("add", "-N", "--", ".", check=False)
        base = "HEAD"
        if self.remote_url:
            branch = self.branch or self._current_branch()
            if self._git("rev-parse", "--verify", f"origin/{branch}", check=False).returncode == 0:
                base = f"origin/{branch}"
        args = ["diff", base]
        if path:
            args += ["--", path]
        return self._git(*args).stdout

    def discard(self, paths: list[str] | None = None) -> SyncResult:
        self.ensure_ready()
        if paths:
            for p in paths:
                tracked = self._git("ls-files", "--error-unmatch", "--", p, check=False).returncode == 0
                if tracked:
                    self._git("checkout", "HEAD", "--", p)
                else:
                    self._git("clean", "-fq", "--", p)
            return SyncResult(True, "discard", f"Discarded local edits to {len(paths)} path(s).", changed_files=paths)
        changed = self._changed_files()
        self._git("reset", "-q", "--hard", "HEAD")
        self._git("clean", "-fdq")
        return SyncResult(True, "discard", f"Discarded {len(changed)} local edit(s).", changed_files=changed)

