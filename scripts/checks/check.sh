#!/bin/bash
# Read-only rule checks: syntax | imports | secrets | all.   ./entry.sh checks [name]
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/../.." && pwd)"
cd "$ROOT"
case "${1:-all}" in
    syntax)  uv run -q python -m py_compile app.py agent/*.py src/*.py integrations/*.py integrations/*/*.py latex/*.py tools/*.py prompts/*.py scripts/tools/*.py && echo "syntax ok" ;;
    imports) uv run -q python "$DIR/check_imports.py" ;;
    secrets) uv run -q python "$DIR/check_secrets.py" ;;
    all)     "$0" syntax && "$0" imports && "$0" secrets ;;
    *)       echo "unknown check '$1' - syntax | imports | secrets | all"; exit 2 ;;
esac
