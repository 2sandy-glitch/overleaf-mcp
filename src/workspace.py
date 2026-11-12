"""File operations on a project's local working copy.

Backend-agnostic: whatever backend syncs the folder, reading and editing work
the same. Every path is checked to stay inside the working copy and away from
.git, so a tool call can never touch files elsewhere on the machine.
"""

import fnmatch
import re
import shutil
import threading
from pathlib import Path

from agent.errors import WorkspaceError
from integrations import Backend, build_backend
from latex import sections as sec
from latex.compile import available_compiler, compile_project
from src import data_dir, get_config
from src.projects import ProjectConfig


class Workspace:
    def __init__(self, pc: ProjectConfig):
        self.config = pc
        self.backend: Backend = build_backend(pc)
        self.lock = threading.RLock()
        self._ready = False

    @property
    def root(self) -> Path:
        return self.backend.workdir

    def ready(self) -> None:
        if not self._ready:
            self.backend.ensure_ready()
            self._ready = True

    # ---- path safety ----------------------------------------------------

    def resolve(self, rel: str, must_exist: bool = True) -> Path:
        if not rel or rel.startswith("/") or rel.startswith("~"):
            raise WorkspaceError(f"Use a path relative to the project root, got '{rel}'.")
        root = self.root.resolve()
        target = (root / rel).resolve()
        if root != target and root not in target.parents:
            raise WorkspaceError(f"Path '{rel}' leaves the project folder.")
        if ".git" in target.relative_to(root).parts:
            raise WorkspaceError("The .git folder is off limits.")
        if must_exist and not target.exists():
            raise WorkspaceError(f"'{rel}' does not exist in the project.")
        return target

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root.resolve()).as_posix()

    # ---- reading --------------------------------------------------------

    def list_files(self, pattern: str = "*") -> list[dict]:
        self.ready()
        out = []
        for p in sorted(self.root.rglob("*")):
            if not p.is_file() or ".git" in p.relative_to(self.root).parts:
                continue
            rel = self.rel(p)
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(p.name, pattern):
                out.append({"path": rel, "bytes": p.stat().st_size})
        return out

    def read(self, rel: str, start_line: int | None = None, end_line: int | None = None) -> str:
        self.ready()
        path = self.resolve(rel)
        if path.is_dir():
            raise WorkspaceError(f"'{rel}' is a folder.")
        if path.stat().st_size > get_config("files")["max_read_bytes"]:
            raise WorkspaceError(f"'{rel}' is too large to read as text.")
        data = path.read_bytes()
        if b"\x00" in data[:4096]:
            raise WorkspaceError(f"'{rel}' is a binary file.")
        text = data.decode("utf-8", errors="replace")
        if start_line or end_line:
            lines = text.splitlines()
            s = max(1, start_line or 1)
            e = min(len(lines), end_line or len(lines))
            return "\n".join(f"{n:>5}  {lines[n - 1]}" for n in range(s, e + 1))
        return text

    def search(self, query: str, regex: bool = False, pattern: str = "*.tex") -> list[dict]:
        self.ready()
        max_hits = get_config("search")["max_hits"]
        text_suffixes = set(get_config("files")["text_suffixes"])
        try:
            rx = re.compile(query if regex else re.escape(query), re.IGNORECASE)
        except re.error as exc:
            raise WorkspaceError(f"Bad regex: {exc}") from exc
        hits = []
        for f in self.list_files(pattern):
            path = self.root / f["path"]
            if path.suffix not in text_suffixes:
                continue
            for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                if rx.search(line):
                    hits.append({"path": f["path"], "line": n, "text": line.strip()[:300]})
                    if len(hits) >= max_hits:
                        return hits
        return hits

    # ---- writing --------------------------------------------------------

    def write(self, rel: str, content: str) -> dict:
        self.ready()
        path = self.resolve(rel, must_exist=False)
        existed = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return {"path": rel, "created": not existed, "bytes": len(content.encode())}

    def edit(self, rel: str, old: str, new: str, replace_all: bool = False) -> dict:
        self.ready()
        text = self.read(rel)
        count = text.count(old)
        if count == 0:
            raise WorkspaceError(f"Text to replace was not found in '{rel}'. Re-read the file; it may have changed.")
        if count > 1 and not replace_all:
            raise WorkspaceError(
                f"Text to replace appears {count} times in '{rel}'. Include more surrounding text, or set replace_all."
            )
        self.resolve(rel).write_text(text.replace(old, new) if replace_all else text.replace(old, new, 1))
        return {"path": rel, "replacements": count if replace_all else 1}

    def delete(self, rel: str) -> dict:
        self.ready()
        path = self.resolve(rel)
        if path == self.root.resolve():
            raise WorkspaceError("Refusing to delete the project root.")
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return {"deleted": rel}

    def move(self, src: str, dst: str) -> dict:
        self.ready()
        s = self.resolve(src)
        d = self.resolve(dst, must_exist=False)
        if d.exists():
            raise WorkspaceError(f"'{dst}' already exists.")
        d.parent.mkdir(parents=True, exist_ok=True)
        s.rename(d)
        return {"from": src, "to": dst}

    def import_file(self, source: str, dest: str) -> dict:
        self.ready()
        src = Path(source).expanduser()
        if not src.is_file():
            raise WorkspaceError(f"Local file '{source}' not found.")
        d = self.resolve(dest, must_exist=False)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, d)
        return {"path": dest, "bytes": d.stat().st_size}

    # ---- sections -------------------------------------------------------

    def outline(self, rel: str | None = None) -> list[dict]:
        rel = rel or self.config.main_file
        text = self.read(rel)
        return [s.as_dict() for s in sec.parse_sections(text, self.config.section_commands)]

    def read_section(self, rel: str | None, title: str) -> dict:
        rel = rel or self.config.main_file
        text = self.read(rel)
        try:
            s = sec.find_section(sec.parse_sections(text, self.config.section_commands), title)
        except ValueError as exc:
            raise WorkspaceError(str(exc)) from exc
        return {**s.as_dict(), "path": rel, "content": sec.section_text(text, s)}

    def replace_section(self, rel: str | None, title: str, content: str) -> dict:
        rel = rel or self.config.main_file
        text = self.read(rel)
        try:
            s = sec.find_section(sec.parse_sections(text, self.config.section_commands), title)
        except ValueError as exc:
            raise WorkspaceError(str(exc)) from exc
        self.resolve(rel).write_text(sec.replace_section(text, s, content))
        return {"path": rel, "replaced": s.title, "old_lines": [s.start_line, s.end_line]}

    # ---- compile --------------------------------------------------------

    def compile(self, main_file: str | None = None, engine: str | None = None, where: str = "auto") -> dict:
        """where: local (latexmk/tectonic here), overleaf (Overleaf builds it), auto (local if TeX is installed)."""
        self.ready()
        main = main_file or self.config.main_file
        self.resolve(main)
        can_remote = hasattr(self.backend, "remote_compile")
        if where == "auto":
            where = "local" if available_compiler() or not can_remote else "overleaf"
        if where == "overleaf":
            if not can_remote:
                raise WorkspaceError("Compiling on Overleaf needs the overleaf-web backend for this project.")
            return self.backend.remote_compile(main, data_dir() / "builds" / self.config.key / "overleaf")
        if where != "local":
            raise WorkspaceError("where must be auto, local or overleaf.")
        engine = engine or get_config("compile")["default_engine"]
        return compile_project(self.root, main, data_dir() / "builds" / self.config.key, engine)
