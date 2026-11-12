"""Sign in to Overleaf and save the session; optionally add a project.

    ./entry.sh login           opens a browser window: sign in as usual, it closes by itself
    ./entry.sh login --paste   paste the overleaf_session2 cookie by hand instead

Manual cookie: sign in at overleaf.com, then DevTools (F12) -> Application/Storage
-> Cookies -> https://www.overleaf.com -> copy the Value of `overleaf_session2`.

The session is written to projects.json (mode 600) and never shown again.
"""

import argparse
import getpass
import json
import os
import re
import sys

from agent.errors import AuthError, OverleafMCPError
from integrations.overleaf.browser_login import capture_session, find_browser
from integrations.overleaf.web_client import OverleafWebClient
from src import get_config, projects_file


def load(path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"default": "", "projects": {}}


def save(path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.chmod(path, 0o600)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"


def signed_in(web_url: str, cookie: str) -> bool:
    client = OverleafWebClient(web_url, cookie)
    try:
        client.whoami()
        return True
    except AuthError:
        return False
    finally:
        client.close()


def get_cookie(web_url: str, paste: bool) -> str:
    if not paste and find_browser():
        print("Opening a browser window. Sign in to Overleaf there; it closes by itself when done.")
        print("(Waiting up to 5 minutes. Ctrl+C to cancel.)")
        return capture_session(web_url, lambda c: signed_in(web_url, c))
    if not paste:
        print("No Chrome/Chromium/Edge/Brave found, so paste the cookie instead.")
    print(__doc__.split("\n\n")[2])
    return getpass.getpass("overleaf_session2 value (input hidden): ").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Sign in to Overleaf for overleaf-mcp.")
    ap.add_argument("--paste", action="store_true", help="paste the cookie by hand instead of opening a browser")
    args = ap.parse_args()

    web_url = get_config("overleaf")["web_url"]
    try:
        cookie = get_cookie(web_url, args.paste)
        if not cookie:
            print("Nothing entered; no change made.")
            return 1
        client = OverleafWebClient(web_url, cookie)
        try:
            who = client.whoami()
            projects = [p for p in client.list_projects() if not p["trashed"] and not p["archived"]]
        finally:
            client.close()
    except OverleafMCPError as exc:
        print(f"✗ {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nCancelled; no change made.")
        return 1
    print(f"✓ signed in (user {who['user_id']}), {len(projects)} active project(s)")

    path = projects_file()
    data = load(path)
    data["overleaf_cookie"] = cookie
    data.setdefault("projects", {})
    known = {p.get("project_id") for p in data["projects"].values()}

    for i, p in enumerate(projects, 1):
        mark = "  (added)" if p["id"] in known else ""
        print(f"  {i:>3}. {p['name']}  [{p['id']}]{mark}")
    choice = input("Add one of these as an overleaf-web project? number, or Enter to skip: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(projects):
        p = projects[int(choice) - 1]
        key = input(f"Short name for it [{slug(p['name'])}]: ").strip() or slug(p["name"])
        main_file = input("Main .tex file [main.tex]: ").strip() or "main.tex"
        data["projects"][key] = {"name": p["name"], "backend": "overleaf-web", "project_id": p["id"], "main_file": main_file}
        if not data.get("default"):
            data["default"] = key
        print(f"✓ added '{key}'" + (" (default)" if data["default"] == key else ""))

    save(path, data)
    print(f"✓ saved to {path} (mode 600)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
