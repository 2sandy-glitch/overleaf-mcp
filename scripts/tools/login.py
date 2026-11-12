"""Save the Overleaf web-session cookie and, optionally, add a project.   ./entry.sh login

Overleaf's sign-in page has a captcha, so this does not take your password.
Sign in to overleaf.com in your browser, then copy the session cookie:
  DevTools (F12) -> Application/Storage -> Cookies -> https://www.overleaf.com
  -> copy the Value of `overleaf_session2`.
The cookie is written to projects.json (mode 600) and never shown again.
"""

import getpass
import json
import os
import re
import sys

from agent.errors import OverleafMCPError
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


def main() -> int:
    print(__doc__.split("\n", 2)[2])
    cookie = getpass.getpass("overleaf_session2 value (input hidden): ").strip()
    if not cookie:
        print("Nothing entered; no change made.")
        return 1

    web_url = get_config("overleaf")["web_url"]
    client = OverleafWebClient(web_url, cookie)
    try:
        who = client.whoami()
        projects = [p for p in client.list_projects() if not p["trashed"] and not p["archived"]]
    except OverleafMCPError as exc:
        print(f"✗ {exc}")
        return 1
    finally:
        client.close()
    print(f"✓ signed in (user {who['user_id']}), {len(projects)} active project(s)")

    path = projects_file()
    data = load(path)
    data["overleaf_cookie"] = cookie
    data.setdefault("projects", {})

    for i, p in enumerate(projects, 1):
        print(f"  {i:>3}. {p['name']}  [{p['id']}]")
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
