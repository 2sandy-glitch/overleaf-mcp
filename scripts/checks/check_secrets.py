"""Rule: no real Overleaf (olp_...) or GitHub (ghp_..., github_pat_...) token is committed anywhere in the repo."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP = {".git", ".venv", "__pycache__", ".pytest_cache"}
TOKEN = re.compile(r"olp_[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}")


def main() -> int:
    hits = []
    for path in ROOT.rglob("*"):
        if path.is_dir() or SKIP & set(path.relative_to(ROOT).parts):
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if TOKEN.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{n}")
    for h in hits:
        print(f"{h}: looks like an access token")
    print("secrets ok" if not hits else f"{len(hits)} possible token(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
