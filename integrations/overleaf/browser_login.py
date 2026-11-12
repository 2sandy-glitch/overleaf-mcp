"""Sign in to Overleaf in a real browser window and capture the session cookie.

Opens Chrome/Chromium/Edge/Brave with a dedicated profile (never your normal
one) on the Overleaf login page. You sign in as usual (password, Google, SSO,
captcha, 2FA). We read the session cookie through the browser's DevTools
protocol on localhost, check it really is signed in, then close the window.
Your password never passes through this program.

The profile is kept (under the data dir, mode 700), so signing in again later
is usually a single click.
"""

import itertools
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import websocket

from agent.errors import AuthError
from src import data_dir, get_config

SESSION_COOKIE = "overleaf_session2"


def display_env(environ: dict | None = None, runtime_dir: str | None = None, x11_dir: str = "/tmp/.X11-unix") -> tuple[dict, list[str]]:
    """(environment, extra browser flags) that let the browser open on the user's desktop.

    Terminals such as VS Code's sometimes start without DISPLAY / WAYLAND_DISPLAY even
    though a desktop session is running. Then we look for the session ourselves:
    the user's Wayland socket first, else an X display the user owns.
    """
    env = dict(os.environ if environ is None else environ)
    if env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"):
        return env, []
    runtime = Path(runtime_dir or env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    sockets = sorted(p for p in runtime.glob("wayland-[0-9]*") if not p.name.endswith(".lock")) if runtime.is_dir() else []
    if sockets:
        env["XDG_RUNTIME_DIR"] = str(runtime)
        env["WAYLAND_DISPLAY"] = sockets[0].name
        return env, ["--ozone-platform=wayland"]
    x11 = Path(x11_dir)
    mine = sorted(p for p in x11.glob("X[0-9]*") if p.stat().st_uid == os.getuid()) if x11.is_dir() else []
    if mine:
        env["DISPLAY"] = ":" + mine[0].name[1:]
        auths = sorted(runtime.glob(".mutter-Xwaylandauth.*"), key=lambda p: p.stat().st_mtime) if runtime.is_dir() else []
        if auths and not env.get("XAUTHORITY"):
            env["XAUTHORITY"] = str(auths[-1])
        return env, ["--ozone-platform=x11"]
    raise AuthError(
        "No desktop display found (are you on SSH or a server?). Run ./entry.sh login --paste to paste the cookie instead."
    )


def _last_error(log: Path) -> str:
    """The most telling line of the browser's own log, for an early-exit message."""
    if not log.exists():
        return ""
    lines = [l for l in log.read_text(errors="replace").splitlines() if "ERROR" in l or "error" in l.lower()]
    noise = ("PHONE_REGISTRATION", "registration_request", "gcm/")
    useful = [l for l in lines if not any(n in l for n in noise)]
    return (useful or lines or [""])[-1].split("] ", 1)[-1].strip()


def find_browser() -> str | None:
    for name in get_config("login")["browsers"]:
        path = shutil.which(name)
        if path:
            return path
    return None


def profile_dir() -> Path:
    path = data_dir() / "browser-profile"
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


class DevTools:
    """Just enough of the Chrome DevTools protocol: send a command, wait for its reply."""

    def __init__(self, ws_url: str, timeout: float):
        # Chrome rejects DevTools websockets that send an Origin it does not allow.
        self.ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
        self._ids = itertools.count(1)

    def send(self, method: str, params: dict | None = None) -> dict:
        msg_id = next(self._ids)
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            reply = json.loads(self.ws.recv())
            if reply.get("id") == msg_id:
                if "error" in reply:
                    raise AuthError(f"Browser refused {method}: {reply['error'].get('message')}")
                return reply.get("result", {})

    def close(self) -> None:
        try:
            self.ws.close()
        except websocket.WebSocketException:
            pass


def _wait_for_port(profile: Path, proc: subprocess.Popen, timeout: float, log: Path) -> str:
    marker = profile / "DevToolsActivePort"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists():
            lines = marker.read_text().split()
            if len(lines) >= 2:
                return f"ws://127.0.0.1:{lines[0]}{lines[1]}"
        if proc.poll() is not None:
            reason = _last_error(log)
            raise AuthError(
                "The browser closed right away"
                + (f" ({reason})" if reason else "")
                + ". If a login window from an earlier run is still open, close it and retry; "
                "otherwise run ./entry.sh login --paste."
            )
        time.sleep(0.2)
    raise AuthError("The browser did not start its DevTools endpoint in time.")


def overleaf_cookies(cookies: list[dict], host: str) -> str:
    """'overleaf_session2=<value>' for the Overleaf host, or '' while there is none."""
    for c in cookies:
        domain = c.get("domain", "").lstrip(".")
        if c.get("name") == SESSION_COOKIE and domain and (host == domain or host.endswith("." + domain)):
            return f"{SESSION_COOKIE}={c['value']}"
    return ""


def capture_session(
    web_url: str, validate, headless: bool = False, on_ready=None, timeout: float | None = None, start_url: str | None = None
) -> str:
    """Open the login page, wait until ``validate(cookie)`` is true, return that cookie string.

    ``validate`` is called only when the session cookie changes (signing in issues a new one).
    ``on_ready(devtools)`` runs once connected (tests use it to plant a cookie).
    """
    browser = find_browser()
    if browser is None:
        raise AuthError("No Chrome, Chromium, Edge or Brave found. Use ./entry.sh login --paste instead.")
    cfg = get_config("login")
    timeout = timeout or cfg["timeout_seconds"]
    host = web_url.split("://", 1)[-1].split("/", 1)[0]

    profile = profile_dir()
    (profile / "DevToolsActivePort").unlink(missing_ok=True)
    args = [
        browser,
        f"--user-data-dir={profile}",
        "--remote-debugging-port=0",
        "--remote-debugging-address=127.0.0.1",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        env, extra = dict(os.environ), ["--headless=new"]
    else:
        env, extra = display_env()
    args += extra
    args.append(start_url or f"{web_url.rstrip('/')}/login")
    log = data_dir() / "browser-login.log"
    with open(log, "w") as log_fh:
        proc = subprocess.Popen(args, stdout=log_fh, stderr=log_fh, env=env, start_new_session=True)

    devtools = None
    try:
        devtools = DevTools(_wait_for_port(profile, proc, 30, log), timeout=30)
        if on_ready:
            on_ready(devtools)
        last_checked = ""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise AuthError("The login window was closed before signing in finished.")
            try:
                cookies = devtools.send("Storage.getCookies").get("cookies", [])
            except (websocket.WebSocketException, OSError) as exc:
                raise AuthError("Lost contact with the login window (was it closed?).") from exc
            cookie = overleaf_cookies(cookies, host)
            if cookie and cookie != last_checked:
                last_checked = cookie
                if validate(cookie):
                    return cookie
            time.sleep(cfg["poll_seconds"])
        raise AuthError(f"Not signed in after {int(timeout)}s; run ./entry.sh login again.")
    finally:
        if devtools is not None:
            try:
                devtools.send("Browser.close")
            except (websocket.WebSocketException, OSError, AuthError):
                pass
            devtools.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
