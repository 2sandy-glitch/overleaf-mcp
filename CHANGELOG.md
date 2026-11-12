# Changelog

## 0.0.2 (2026-11-12)

- **New `overleaf-web` backend that works on free Overleaf plans.** It signs in with your browser session cookie. On pull, it downloads the project zip into a local mirror repo. On push, it uploads only the files you changed and deletes only the ones you removed, including folders left empty. Conflict checks reuse the existing git rebase, so a co-author's change to the same lines still blocks the push.
- **`compile where=overleaf`.** Overleaf builds the project and the PDF and log are downloaded to `~/.local/share/overleaf-mcp/builds/<project>/overleaf/`.
- **New `list_overleaf_projects` tool** to find project IDs.
- **New `./entry.sh login`** saves the cookie (mode 600) and adds a project interactively. `setup` now creates an empty `projects.json` instead of copying the example.
- Projects can share one account cookie (`overleaf_cookie` at the top of `projects.json`, or the `OVERLEAF_COOKIE` env var).
- The testsuite has a fake Overleaf, which covers push, conflicts, folders, delete, remote compile and an expired session.

## 0.0.1 (2026-11-12)

- First version: Overleaf Git bridge, `git` and `local` backends. Covers file and section editing, local compile, and diff and push with conflict refusal, plus the `tailor_resume` and `edit_document` prompts.
- Restructured into the agentic-system layout (`app.py`, `entry.sh`, `agent/`, `src/`, `integrations/`, `tools/`, `prompts/`, `scripts/`).
