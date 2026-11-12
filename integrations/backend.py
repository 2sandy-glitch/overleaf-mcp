"""The contract every integration implements.

An integration owns one thing: keeping a local working copy (``workdir``) in
sync with wherever the project really lives (Overleaf, another git host, a
plain folder). Reading and editing happen on the working copy through
src/workspace.py, so tools never depend on the integration.

Edits stay local until ``push``; nothing reaches Overleaf by accident.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SyncResult:
    ok: bool
    action: str
    message: str
    changed_files: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "action": self.action,
            "message": self.message,
            "changed_files": self.changed_files,
            "conflicts": self.conflicts,
        }


class Backend(ABC):
    kind: str = "abstract"

    def __init__(self, workdir: Path):
        self.workdir = workdir

    @abstractmethod
    def ensure_ready(self) -> None:
        """Make sure the working copy exists (clone / init on first use)."""

    @abstractmethod
    def pull(self) -> SyncResult:
        """Bring remote changes into the working copy, keeping local edits."""

    @abstractmethod
    def push(self, message: str) -> SyncResult:
        """Publish local edits. Must refuse rather than overwrite remote work."""

    @abstractmethod
    def status(self) -> dict:
        """Local changes not yet pushed, plus sync state."""

    @abstractmethod
    def diff(self, path: str | None = None) -> str:
        """Unified diff of local changes not yet pushed."""

    @abstractmethod
    def discard(self, paths: list[str] | None = None) -> SyncResult:
        """Throw away local edits (all, or only the given paths)."""
