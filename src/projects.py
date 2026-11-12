"""The user's projects, from projects.json or the single-project env vars.

Tokens live only in that file / env and are never returned by any tool.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from agent.errors import ConfigError
from src import get_config, projects_file

BACKENDS = ("overleaf-web", "overleaf-git", "git", "local")


@dataclass
class ProjectConfig:
    key: str
    backend: str
    name: str = ""
    main_file: str = "main.tex"
    project_id: str = ""
    token: str = field(default="", repr=False)
    git_host: str = ""
    web_url: str = ""
    cookie: str = field(default="", repr=False)
    remote_url: str = ""
    branch: str = ""
    path: str = ""
    section_commands: list[str] = field(default_factory=list)

    def public(self) -> dict:
        """Safe-to-show view: never includes the token."""
        info = {"key": self.key, "name": self.name or self.key, "backend": self.backend, "main_file": self.main_file}
        if self.project_id:
            info["project_id"] = self.project_id
            info["url"] = get_config("overleaf")["project_url"] + self.project_id
        if self.path:
            info["path"] = self.path
        return info


@dataclass
class Projects:
    default: str
    items: dict[str, ProjectConfig]

    def get(self, key: str | None) -> ProjectConfig:
        key = key or self.default
        if not key:
            raise ConfigError(f"No project given and no default set. Add one to {projects_file()}.")
        if key not in self.items:
            known = ", ".join(sorted(self.items)) or "none"
            raise ConfigError(f"Unknown project '{key}'. Configured projects: {known}.")
        return self.items[key]


def _parse(key: str, raw: dict, shared_cookie: str = "") -> ProjectConfig:
    backend = raw.get("backend", "overleaf-git")
    pc = ProjectConfig(
        key=key,
        backend=backend,
        name=raw.get("name", ""),
        main_file=raw.get("main_file", "main.tex"),
        project_id=raw.get("project_id", raw.get("projectId", "")),
        token=raw.get("token", raw.get("gitToken", "")),
        git_host=raw.get("git_host") or os.environ.get("OVERLEAF_GIT_HOST") or get_config("overleaf")["git_host"],
        web_url=raw.get("web_url") or os.environ.get("OVERLEAF_WEB_URL") or get_config("overleaf")["web_url"],
        cookie=raw.get("cookie") or shared_cookie,
        remote_url=raw.get("remote_url", ""),
        branch=raw.get("branch", ""),
        path=str(Path(raw["path"]).expanduser()) if raw.get("path") else "",
        section_commands=raw.get("section_commands") or list(get_config("latex")["section_commands"]),
    )
    if backend not in BACKENDS:
        raise ConfigError(f"Project '{key}': unknown backend '{backend}' (use one of {', '.join(BACKENDS)}).")
    if backend == "overleaf-web" and not pc.project_id:
        raise ConfigError(f"Project '{key}': overleaf-web needs project_id.")
    if backend == "overleaf-git" and not (pc.project_id and pc.token):
        raise ConfigError(f"Project '{key}': overleaf-git needs project_id and token.")
    if backend == "git" and not pc.remote_url:
        raise ConfigError(f"Project '{key}': git backend needs remote_url.")
    if backend == "local" and not pc.path:
        raise ConfigError(f"Project '{key}': local backend needs path.")
    return pc


def load_projects() -> Projects:
    items: dict[str, ProjectConfig] = {}
    default = ""

    path = projects_file()
    if path.exists():
        try:
            raw = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
        shared_cookie = os.environ.get("OVERLEAF_COOKIE") or raw.get("overleaf_cookie", "")
        for key, item in (raw.get("projects") or {}).items():
            items[key] = _parse(key, item, shared_cookie)
        default = raw.get("default", "")

    env_id = os.environ.get("OVERLEAF_PROJECT_ID")
    env_token = os.environ.get("OVERLEAF_GIT_TOKEN")
    env_cookie = os.environ.get("OVERLEAF_COOKIE")
    if env_id and env_cookie and not env_token:
        items["default"] = _parse(
            "default",
            {"backend": "overleaf-web", "project_id": env_id, "main_file": os.environ.get("OVERLEAF_MAIN_FILE", "main.tex")},
            env_cookie,
        )
        default = default or "default"
    elif env_id and env_token:
        items["default"] = _parse(
            "default",
            {"project_id": env_id, "token": env_token, "main_file": os.environ.get("OVERLEAF_MAIN_FILE", "main.tex")},
        )
        default = default or "default"

    if not default and len(items) == 1:
        default = next(iter(items))
    return Projects(default=default, items=items)


def shared_cookie() -> str:
    """The account-wide session cookie (projects.json overleaf_cookie or OVERLEAF_COOKIE)."""
    if os.environ.get("OVERLEAF_COOKIE"):
        return os.environ["OVERLEAF_COOKIE"]
    path = projects_file()
    if not path.exists():
        return ""
    try:
        return json.loads(path.read_text()).get("overleaf_cookie", "")
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
