"""Minimal Socket.IO 0.9 client: joins a project once to read its file tree.

The Overleaf editor's real-time socket is the only place that hands out the
folder / doc / file ids that upload, delete and compile need. We connect,
wait for ``joinProjectResponse``, and disconnect. Nothing is ever sent to
the document stream, so this cannot change the project.
"""

import json
import time

import httpx
import websocket

from agent.errors import AuthError, BackendError

JOIN_EVENT = "joinProjectResponse"
REJECT_EVENT = "connectionRejected"


def parse_handshake(text: str) -> tuple[str, list[str]]:
    """'<sid>:<heartbeat>:<close>:<transports>' -> (sid, transports)."""
    parts = text.strip().split(":")
    if len(parts) < 4 or not parts[0]:
        raise BackendError("Overleaf sent an unexpected Socket.IO handshake.")
    return parts[0], parts[3].split(",")


def parse_event(packet: str) -> tuple[str, list] | None:
    """'5:<id>:<endpoint>:{json}' -> (name, args); None for any other packet."""
    if not packet.startswith("5:"):
        return None
    pieces = packet.split(":", 3)
    if len(pieces) < 4:
        return None
    try:
        body = json.loads(pieces[3])
    except json.JSONDecodeError:
        return None
    return body.get("name", ""), body.get("args") or []


def join_project(client: httpx.Client, base_url: str, project_id: str, user_agent: str, timeout: float) -> dict:
    """Returns the joinProject payload's ``project`` (with rootFolder, rootDoc_id...)."""
    resp = client.get(
        f"{base_url}/socket.io/1/",
        params={"projectId": project_id, "t": str(int(time.time() * 1000))},
        headers={"accept": "text/plain"},
    )
    if resp.status_code == 401 or resp.url.path.startswith("/login"):
        raise AuthError("Overleaf session expired. Run ./entry.sh login again.")
    if resp.status_code != 200:
        raise BackendError(f"Socket.IO handshake returned HTTP {resp.status_code}.")
    sid, transports = parse_handshake(resp.text)
    if "websocket" not in transports:
        raise BackendError("Overleaf did not offer the websocket transport.")

    # Includes any load-balancer cookie the handshake just set: the socket must hit the same backend.
    cookie = "; ".join(f"{c.name}={c.value}" for c in client.cookies.jar)
    ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://") + f"/socket.io/1/websocket/{sid}"
    try:
        ws = websocket.create_connection(
            ws_url,
            header=[f"Origin: {base_url}", f"User-Agent: {user_agent}"],
            cookie=cookie,
            timeout=timeout,
        )
    except (websocket.WebSocketException, OSError) as exc:
        raise BackendError(f"Could not open the Overleaf project socket: {exc}") from exc

    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            packet = ws.recv()
            if packet.startswith("2::"):
                ws.send("2::")
                continue
            if packet.startswith("0::"):
                raise BackendError("Overleaf closed the project socket before answering.")
            event = parse_event(packet)
            if event is None:
                continue
            name, args = event
            if name == JOIN_EVENT and args:
                project = args[0].get("project")
                if not isinstance(project, dict) or "rootFolder" not in project:
                    raise BackendError("joinProject answered in a shape this version does not read.")
                return project
            if name == REJECT_EVENT:
                raise AuthError("Overleaf refused the project socket (session expired or no access). Run ./entry.sh login.")
        raise BackendError("Timed out waiting for Overleaf to send the project tree.")
    except websocket.WebSocketTimeoutException as exc:
        raise BackendError("Timed out waiting for Overleaf to send the project tree.") from exc
    finally:
        ws.close()


def flatten_tree(root_folder: list[dict]) -> dict[str, dict]:
    """rootFolder -> {"path": {"id", "type": doc|file|folder}}; the root folder is path ''."""
    out: dict[str, dict] = {}

    def walk(folder: dict, prefix: str) -> None:
        out[prefix] = {"id": folder["_id"], "type": "folder"}
        for doc in folder.get("docs") or []:
            out[f"{prefix}{doc['name']}"] = {"id": doc["_id"], "type": "doc"}
        for ref in folder.get("fileRefs") or []:
            out[f"{prefix}{ref['name']}"] = {"id": ref["_id"], "type": "file"}
        for sub in folder.get("folders") or []:
            walk(sub, f"{prefix}{sub['name']}/")

    if root_folder:
        walk(root_folder[0], "")
    # Folder keys without the trailing slash, for lookups by dirname.
    return {k.rstrip("/") if v["type"] == "folder" else k: v for k, v in out.items()}
