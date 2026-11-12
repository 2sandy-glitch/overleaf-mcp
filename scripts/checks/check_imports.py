"""Rule: every import sits at the top of its file, never inside a function or class."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDERS = ["agent", "src", "integrations", "latex", "tools", "prompts", "scripts"]


def nested_imports(path: Path) -> list[int]:
    tree = ast.parse(path.read_text())
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for inner in ast.walk(node):
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    bad.append(inner.lineno)
    return bad


def main() -> int:
    files = [ROOT / "app.py"] + [p for f in FOLDERS for p in (ROOT / f).rglob("*.py")]
    failures = 0
    for path in files:
        for line in nested_imports(path):
            print(f"{path.relative_to(ROOT)}:{line}: import inside a function/class")
            failures += 1
    print("imports ok" if not failures else f"{failures} nested import(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
