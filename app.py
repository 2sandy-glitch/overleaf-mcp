"""overleaf-mcp entry point: runs the MCP server over stdio.

    uv run python app.py             # serve (what Claude Code launches)
    uv run python app.py --version
"""

import sys

from agent.system import build_server
from src import VERSION


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(VERSION)
        return
    build_server().run("stdio")


if __name__ == "__main__":
    main()
