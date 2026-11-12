#!/bin/bash
# =============================================================================
# overleaf-mcp - Entry Script
# =============================================================================
# Usage:
#   ./entry.sh setup        - Install dependencies (uv sync) and create the projects.json skeleton
#   ./entry.sh login        - Sign in to Overleaf in a browser window (--paste: paste the cookie) and pick a project
#   ./entry.sh start        - Run the MCP server on stdio (what Claude Code launches)
#   ./entry.sh register     - Add/refresh the server in Claude Code (user scope)
#   ./entry.sh unregister   - Remove it from Claude Code
#   ./entry.sh status       - Version, config file, Claude Code registration
#   ./entry.sh checks       - Read-only rule checks (scripts/checks/check.sh)
#   ./entry.sh testsuite    - Run the test suite (scripts/testsuite)
#   ./entry.sh version      - Print the version
# =============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/overleaf-mcp"
PROJECTS_FILE="${OVERLEAF_MCP_CONFIG:-$CONFIG_DIR/projects.json}"
SERVER_NAME="overleaf"

print_ok()   { echo -e "${GREEN}✓${NC} $1"; }
print_info() { echo -e "${YELLOW}➜${NC} $1"; }
print_err()  { echo -e "${RED}✗${NC} $1" >&2; }

need() {
    command -v "$1" &> /dev/null || { print_err "$1 is not installed"; exit 1; }
}

do_setup() {
    need uv
    need git
    uv sync -q
    print_ok "dependencies installed"
    if [ -f "$PROJECTS_FILE" ]; then
        print_ok "projects file exists: $PROJECTS_FILE"
    else
        mkdir -p "$(dirname "$PROJECTS_FILE")"
        (umask 077; echo '{"default": "", "projects": {}}' > "$PROJECTS_FILE")
        print_info "created $PROJECTS_FILE (mode 600) - run ./entry.sh login next (see projects.example.json for other backends)"
    fi
    command -v latexmk &> /dev/null || command -v tectonic &> /dev/null \
        || print_info "no local TeX compiler; 'compile' tool will be skipped (sudo apt install latexmk texlive-latex-extra)"
}

do_register() {
    need claude
    claude mcp remove "$SERVER_NAME" --scope user &> /dev/null || true
    claude mcp add "$SERVER_NAME" --scope user -- uv run --directory "$SCRIPT_DIR" python app.py
    print_ok "registered '$SERVER_NAME' in Claude Code - restart Claude Code to pick it up"
}

do_status() {
    echo "version : $(uv run -q python app.py --version)"
    if [ -f "$PROJECTS_FILE" ]; then echo "projects: $PROJECTS_FILE"; else echo "projects: missing ($PROJECTS_FILE) - run ./entry.sh setup"; fi
    if command -v claude &> /dev/null; then claude mcp get "$SERVER_NAME" 2>&1 | sed -n '1,4p'; fi
}

case "$1" in
    setup)      do_setup ;;
    login)      shift; uv run -q python -m scripts.tools.login "$@" ;;
    start)      exec uv run -q python app.py ;;
    register)   do_register ;;
    unregister) need claude; claude mcp remove "$SERVER_NAME" --scope user ;;
    status)     do_status ;;
    checks)     shift; bash scripts/checks/check.sh "$@" ;;
    testsuite)  shift; uv run -q pytest -q scripts/testsuite "$@" ;;
    version)    uv run -q python app.py --version ;;
    *)
        sed -n '5,14p' "$0" | sed 's/^# //'
        exit 2
        ;;
esac
