"""Overleaf's web endpoints, signed in with the user's own browser session cookie.

These are the same endpoints the Overleaf web editor uses. They are not a
public API and may change; keep request volume low. Works on free plans.

Session: the ``overleaf_session2`` cookie (or a full ``Cookie:`` header copied
from the browser). It lasts about five days from its last use.
"""

import html
import re
import time
from pathlib import Path

import httpx

from agent.errors import AuthError, BackendError
from integrations.overleaf import socketio
from src import VERSION, get_config

SESSION_COOKIE = "overleaf_session2"
META_TAG = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
# Tests point this at a fake Overleaf (httpx.MockTransport); None = the real network.
default_transport: httpx.BaseTransport | None = None
META_ATTR = re.compile(r'([\w:-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')


def parse_cookie(raw: str) -> dict[str, str]:
    """Accepts 'name=value; other=x' or a bare overleaf_session2 value."""
    raw = raw.strip()
    if raw.lower().startswith("cookie:"):
        raw = raw[7:].strip()
    if "=" not in raw:
        return {SESSION_COOKIE: raw}
    out = {}
    for part in raw.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def parse_meta(page: str) -> dict[str, str]:
    meta = {}
    for tag in META_TAG.findall(page):
        attrs = {m.group(1).lower(): html.unescape(m.group(2) if m.group(2) is not None else m.group(3)) for m in META_ATTR.finditer(tag)}
        if "name" in attrs and "content" in attrs:
            meta[attrs["name"]] = attrs["content"]
    return meta


class OverleafWebClient:
    def __init__(self, base_url: str, cookie: str, transport: httpx.BaseTransport | None = None):
        if not cookie:
            raise AuthError("No Overleaf session cookie configured. Run ./entry.sh login.")
        cfg = get_config("web")
        self.base_url = base_url.rstrip("/")
        self.timeout = cfg["timeout_seconds"]
        self.user_agent = f"overleaf-mcp/{VERSION}"
        host = httpx.URL(self.base_url).host
        self.http = httpx.Client(
            base_url=self.base_url,
            headers={"user-agent": self.user_agent},
            timeout=self.timeout,
            follow_redirects=True,
            transport=transport or default_transport,
        )
        for name, value in parse_cookie(cookie).items():
            self.http.cookies.set(name, value, domain=host)
        self._csrf = ""
        self.user_id = ""

    def close(self) -> None:
        self.http.close()

    # ---- plumbing -------------------------------------------------------

    def _check(self, resp: httpx.Response, what: str) -> httpx.Response:
        if resp.status_code in (401, 403) or resp.url.path.startswith("/login"):
            raise AuthError(f"Overleaf refused {what}: session expired or no access. Run ./entry.sh login.")
        if resp.status_code == 429:
            raise BackendError(f"Overleaf is rate limiting ({what}); wait a minute and retry.")
        if resp.status_code >= 400:
            detail = resp.text[:200].strip()
            raise BackendError(f"Overleaf {what} failed with HTTP {resp.status_code}: {detail}")
        return resp

    def _request(self, method: str, path: str, what: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        if method != "GET":
            headers["x-csrf-token"] = self.csrf()
        try:
            resp = self.http.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise BackendError(f"Could not reach Overleaf ({what}): {exc}") from exc
        return self._check(resp, what)

    def csrf(self) -> str:
        """CSRF token + user id, read once from the signed-in dashboard page."""
        if not self._csrf:
            resp = self._check(self.http.get("/project"), "opening the dashboard")
            meta = parse_meta(resp.text)
            self._csrf = meta.get("ol-csrfToken", "")
            self.user_id = meta.get("ol-user_id", "")
            if not self._csrf:
                raise AuthError("Overleaf did not return a signed-in page. Run ./entry.sh login.")
        return self._csrf

    # ---- account --------------------------------------------------------

    def whoami(self) -> dict:
        self.csrf()
        return {"user_id": self.user_id, "base_url": self.base_url}

    def list_projects(self) -> list[dict]:
        data = self._request("POST", "/api/project", "listing projects", json={}).json()
        out = []
        for p in data.get("projects") or []:
            out.append(
                {
                    "id": p.get("id") or p.get("_id"),
                    "name": p.get("name"),
                    "access": p.get("accessLevel"),
                    "last_updated": p.get("lastUpdated"),
                    "archived": bool(p.get("archived")),
                    "trashed": bool(p.get("trashed")),
                }
            )
        return out

    # ---- project content ------------------------------------------------

    def download_zip(self, project_id: str, dest: Path) -> Path:
        resp = self._request("GET", f"/Project/{project_id}/download/zip", "downloading the project")
        dest.write_bytes(resp.content)
        return dest

    def tree(self, project_id: str) -> tuple[dict[str, dict], dict]:
        """({path: {id, type}}, raw project) from the editor socket."""
        project = socketio.join_project(self.http, self.base_url, project_id, self.user_agent, self.timeout)
        return socketio.flatten_tree(project["rootFolder"]), project

    def create_folder(self, project_id: str, parent_id: str, name: str) -> str:
        data = self._request(
            "POST", f"/project/{project_id}/folder", f"creating folder {name}", json={"name": name, "parent_folder_id": parent_id}
        ).json()
        return data["_id"]

    def upload(self, project_id: str, folder_id: str, name: str, content: bytes) -> dict:
        """Create or replace a file. Replacing a .tex doc goes through Overleaf's diff, so its history is kept."""
        resp = self._request(
            "POST",
            f"/project/{project_id}/upload",
            f"uploading {name}",
            params={"folder_id": folder_id},
            files={"qqfile": (name, content, "application/octet-stream")},
            data={"name": name},
        )
        body = resp.json()
        if body.get("success") is False:
            raise BackendError(f"Overleaf rejected {name}: {body.get('error', 'unknown reason')}")
        return body

    def delete(self, project_id: str, entity_type: str, entity_id: str, what: str) -> None:
        self._request("DELETE", f"/project/{project_id}/{entity_type}/{entity_id}", f"deleting {what}")

    # ---- compile --------------------------------------------------------

    def compile(self, project_id: str, root_doc_id: str, root_path: str) -> dict:
        return self._request(
            "POST",
            f"/project/{project_id}/compile",
            "compiling",
            params={"file_line_errors": "true"},
            json={
                "rootDoc_id": root_doc_id,
                "rootResourcePath": root_path,
                "check": "silent",
                "incrementalCompilesEnabled": True,
            },
            timeout=get_config("compile")["remote_timeout_seconds"],
        ).json()

    def fetch_output(self, output_url: str, clsi_server_id: str | None) -> bytes:
        params = {"clsiserverid": clsi_server_id} if clsi_server_id else {}
        params["t"] = str(int(time.time()))
        return self._request("GET", output_url, "downloading compile output", params=params).content
