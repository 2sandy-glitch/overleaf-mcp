"""An in-process fake of the Overleaf web endpoints we call, for the testsuite.

HTTP goes through httpx.MockTransport; the editor socket (join_project) is
replaced by `join_project`, which builds the same rootFolder shape.
"""

import io
import itertools
import json
import re
import zipfile
from pathlib import PurePosixPath

import httpx

PROJECT_ID = "p" * 24
CSRF = "csrf-token-1"
COOKIE = "s%3Asession"


class FakeOverleaf:
    def __init__(self, files: dict[str, bytes]):
        self.files = dict(files)
        self._ids = itertools.count(1)
        self.ids: dict[str, str] = {}
        self.folders: dict[str, str] = {"": self._new_id()}
        for path in self.files:
            self._register(path)
        self.signed_in = True
        self.calls: list[str] = []

    def _new_id(self) -> str:
        return f"{next(self._ids):024x}"

    def _register(self, path: str) -> None:
        self.ids.setdefault(path, self._new_id())
        parent = str(PurePosixPath(path).parent)
        parts = [] if parent == "." else parent.split("/")
        for i in range(1, len(parts) + 1):
            self.folders.setdefault("/".join(parts[:i]), self._new_id())

    def _path_of(self, entity_id: str) -> str | None:
        return next((p for p, i in {**self.ids, **self.folders}.items() if i == entity_id), None)

    # ---- socket stand-in ------------------------------------------------

    def join_project(self, client, base_url, project_id, user_agent, timeout) -> dict:
        def folder(path: str) -> dict:
            prefix = f"{path}/" if path else ""
            kids = [p for p in self.folders if p and str(PurePosixPath(p).parent) == (path or ".")]
            here = [p for p in self.files if str(PurePosixPath(p).parent) == (path or ".")]
            return {
                "_id": self.folders[path],
                "name": PurePosixPath(path).name or "rootFolder",
                "docs": [{"_id": self.ids[p], "name": p[len(prefix):]} for p in here if p.endswith(".tex")],
                "fileRefs": [{"_id": self.ids[p], "name": p[len(prefix):]} for p in here if not p.endswith(".tex")],
                "folders": [folder(k) for k in kids],
            }

        main = next((i for p, i in self.ids.items() if p == "main.tex"), None)
        return {"_id": project_id, "rootDoc_id": main, "rootFolder": [folder("")]}

    # ---- HTTP -----------------------------------------------------------

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, req: httpx.Request) -> httpx.Response:
        path, method = req.url.path, req.method
        self.calls.append(f"{method} {path}")
        if path == "/login":
            return httpx.Response(200, text="<html>login</html>")
        if not self.signed_in or COOKIE not in req.headers.get("cookie", ""):
            return httpx.Response(302, headers={"location": "/login"})
        if method != "GET" and req.headers.get("x-csrf-token") != CSRF:
            return httpx.Response(403, text="bad csrf")

        if path == "/project" and method == "GET":
            return httpx.Response(200, text=f'<meta name="ol-csrfToken" content="{CSRF}"><meta name="ol-user_id" content="u1">')
        if path == "/api/project":
            return httpx.Response(200, json={"projects": [{"id": PROJECT_ID, "name": "My Resume", "accessLevel": "owner"}]})
        if path == f"/Project/{PROJECT_ID}/download/zip":
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                for p, data in self.files.items():
                    zf.writestr(p, data)
            return httpx.Response(200, content=buf.getvalue())
        if path == f"/project/{PROJECT_ID}/upload":
            folder = self._path_of(req.url.params["folder_id"])
            name, content = parse_multipart(req)
            full = f"{folder}/{name}" if folder else name
            self.files[full] = content
            self._register(full)
            return httpx.Response(200, json={"success": True, "entity_id": self.ids[full], "entity_type": "doc"})
        if path == f"/project/{PROJECT_ID}/folder":
            body = json.loads(req.content)
            parent = self._path_of(body["parent_folder_id"])
            full = f"{parent}/{body['name']}" if parent else body["name"]
            self.folders[full] = self._new_id()
            return httpx.Response(200, json={"_id": self.folders[full], "name": body["name"]})
        m = re.fullmatch(rf"/project/{PROJECT_ID}/(doc|file|folder)/(\w+)", path)
        if m and method == "DELETE":
            target = self._path_of(m.group(2))
            if m.group(1) == "folder":
                self.folders.pop(target)
                for p in [p for p in self.files if p.startswith(target + "/")]:
                    self.files.pop(p)
            else:
                self.files.pop(target)
                self.ids.pop(target)
            return httpx.Response(204)
        if path == f"/project/{PROJECT_ID}/compile":
            out = f"/project/{PROJECT_ID}/user/u1/build/b1/output"
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "clsiServerId": "clsi-1",
                    "outputFiles": [
                        {"path": "output.pdf", "url": f"{out}/output.pdf", "build": "b1"},
                        {"path": "output.log", "url": f"{out}/output.log", "build": "b1"},
                    ],
                },
            )
        if path.endswith("/output/output.pdf"):
            return httpx.Response(200, content=b"%PDF-1.5 fake")
        if path.endswith("/output/output.log"):
            return httpx.Response(200, text="LaTeX Warning: fake warning\n")
        return httpx.Response(404, text=f"fake has no {method} {path}")


def parse_multipart(req: httpx.Request) -> tuple[str, bytes]:
    boundary = req.headers["content-type"].split("boundary=")[1].encode()
    name, content = "", b""
    for part in req.content.split(b"--" + boundary):
        if b"\r\n\r\n" not in part:
            continue
        head, body = part.split(b"\r\n\r\n", 1)
        body = body[:-2] if body.endswith(b"\r\n") else body
        if b'name="qqfile"' in head:
            content = body
        elif b'name="name"' in head:
            name = body.decode()
    return name, content
