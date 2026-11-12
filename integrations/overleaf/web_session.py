"""Overleaf through the web session: works on free plans, no Git integration needed.

How sync works, reusing the git logic for conflict safety:

    Overleaf ──zip download──▶ mirror repo (one commit per snapshot of Overleaf)
                                   ▲  │ git pull --rebase
                       git push    │  ▼
                                 working copy (where all edits happen)

* pull  = snapshot Overleaf into the mirror, then rebase local edits on it.
* push  = snapshot again, rebase (a clash with a co-author's edit refuses the
  push), upload only the files that changed, delete only the files removed,
  then record the result in the mirror.
"""

import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from agent.errors import BackendError
from integrations.backend import SyncResult
from integrations.git.client import GitBackend
from integrations.overleaf.remote_compile import compile_on_overleaf, unpushed_note
from integrations.overleaf.web_client import OverleafWebClient

MIRROR_BRANCH = "main"


class WebSessionBackend(GitBackend):
    def __init__(self, workdir: Path, mirror_dir: Path, project_id: str, client_factory, main_file: str):
        super().__init__(workdir, remote_url=str(mirror_dir), branch=MIRROR_BRANCH, label="overleaf-web")
        self.mirror_dir = mirror_dir
        self.project_id = project_id
        self._client_factory = client_factory
        self.main_file = main_file

    # ---- mirror ---------------------------------------------------------

    def _mirror_git(self, *args: str, check: bool = True):
        return self._git(*args, cwd=self.mirror_dir, check=check)

    def _ensure_mirror(self) -> None:
        if (self.mirror_dir / ".git").exists():
            return
        self.mirror_dir.mkdir(parents=True, exist_ok=True)
        self._mirror_git("init", "-q", "-b", MIRROR_BRANCH)
        # Lets the working copy push into the mirror's checked-out branch.
        self._mirror_git("config", "receive.denyCurrentBranch", "updateInstead")
        self._mirror_git("config", "user.name", "overleaf-snapshot")
        self._mirror_git("config", "user.email", "overleaf-snapshot@localhost")
        self._snapshot(client=None, allow_empty=True)

    def _snapshot(self, client: OverleafWebClient | None, allow_empty: bool = False) -> list[str]:
        """Replace the mirror's files with Overleaf's current zip; commit if anything changed."""
        own = client is None
        client = client or self._client_factory()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                zpath = client.download_zip(self.project_id, Path(tmp) / "project.zip")
                extract = Path(tmp) / "x"
                with zipfile.ZipFile(zpath) as zf:
                    for member in zf.namelist():
                        target = (extract / member).resolve()
                        if extract.resolve() not in target.parents and target != extract.resolve():
                            raise BackendError(f"Overleaf zip has an unsafe path: {member}")
                    zf.extractall(extract)
                for child in self.mirror_dir.iterdir():
                    if child.name == ".git":
                        continue
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
                if extract.exists():
                    shutil.copytree(extract, self.mirror_dir, dirs_exist_ok=True)
        finally:
            if own:
                client.close()
        self._mirror_git("add", "-A")
        changed = self._mirror_git("diff", "--cached", "--name-only").stdout.split()
        if changed or allow_empty:
            self._mirror_git("commit", "-q", "--allow-empty", "-m", "Overleaf snapshot")
        return changed

    # ---- contract -------------------------------------------------------

    def ensure_ready(self) -> None:
        self._ensure_mirror()
        super().ensure_ready()

    def pull(self) -> SyncResult:
        self.ensure_ready()
        self._snapshot(client=None)
        return super().pull()

    def push(self, message: str) -> SyncResult:
        self.ensure_ready()
        self._snapshot(client=None)
        return super().push(message)

    def _publish(self, branch: str, ahead: int) -> SyncResult:
        """Upload what changed between the Overleaf snapshot and the rebased working copy."""
        rows = self._git("diff", "--name-status", "--no-renames", f"origin/{branch}", "HEAD").stdout.splitlines()
        changes = [(r.split("\t", 1)[0], r.split("\t", 1)[1]) for r in rows if "\t" in r]
        if not changes:
            return SyncResult(True, "push", "No local changes to push.")

        client = self._client_factory()
        done: list[str] = []
        try:
            tree, _ = client.tree(self.project_id)
            for status, path in changes:
                if status == "D":
                    entity = tree.get(path)
                    if entity:
                        client.delete(self.project_id, entity["type"], entity["id"], path)
                    done.append(path)
                    continue
                folder_id = self._ensure_folders(client, tree, str(PurePosixPath(path).parent))
                name = PurePosixPath(path).name
                client.upload(self.project_id, folder_id, name, (self.workdir / path).read_bytes())
                done.append(path)
            self._remove_empty_folders(client, tree, [p for s, p in changes if s == "D"])
        except BackendError as exc:
            left = [p for _, p in changes if p not in done]
            return SyncResult(
                False,
                "push",
                f"Stopped part-way: {exc} Applied {len(done)} of {len(changes)} change(s); "
                "run push again to send the rest (already-sent files will show as unchanged).",
                changed_files=done,
                conflicts=left,
            )
        finally:
            client.close()

        self._git("push", "origin", f"HEAD:{branch}")
        return SyncResult(True, "push", f"Sent {len(done)} file change(s) to Overleaf.", changed_files=done)

    def _ensure_folders(self, client: OverleafWebClient, tree: dict, folder: str) -> str:
        folder = "" if folder == "." else folder
        if folder in tree:
            return tree[folder]["id"]
        parent = str(PurePosixPath(folder).parent)
        parent_id = self._ensure_folders(client, tree, parent)
        new_id = client.create_folder(self.project_id, parent_id, PurePosixPath(folder).name)
        tree[folder] = {"id": new_id, "type": "folder"}
        return new_id

    def _remove_empty_folders(self, client: OverleafWebClient, tree: dict, deleted: list[str]) -> None:
        """A folder whose last file was deleted locally is deleted on Overleaf too (git has no empty folders)."""
        candidates = {str(PurePosixPath(p).parent) for p in deleted} - {"."}
        for folder in sorted(candidates, key=len, reverse=True):
            still_used = self._git("ls-tree", "-r", "--name-only", "HEAD", "--", folder).stdout.strip()
            if not still_used and folder in tree:
                client.delete(self.project_id, "folder", tree[folder]["id"], folder)

    # ---- remote compile -------------------------------------------------

    can_remote_compile = True

    def remote_compile(self, main_file: str | None, out_dir: Path) -> dict:
        """Compile on Overleaf (what is on Overleaf now, not unpushed edits) and download the PDF + log."""
        self.ensure_ready()
        client = self._client_factory()
        try:
            result = compile_on_overleaf(client, self.project_id, main_file or self.main_file, out_dir)
        finally:
            client.close()
        return {**result, "note": unpushed_note(self.status())}
