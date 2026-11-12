# Architecture (v0.2.0)

The folder layout follows the ACI agentic-system: flat top-level folders by role, `app.py` + `entry.sh` at the root, `config.json` for settings, one folder per integration.

```
overleaf-MCP/
├── app.py                  entry point: runs the MCP server on stdio
├── entry.sh                setup | login | start | register | unregister | status | checks | testsuite | version
├── config.json             non-secret app settings (git host, timeouts, limits, heading commands)
├── projects.example.json   template for ~/.config/overleaf-mcp/projects.json (holds tokens)
├── agent/                  server core
│   ├── system.py             builds the MCPServer: tools + prompts + instructions
│   ├── registry.py           one Workspace per project, per-project lock, error → tool error
│   └── errors.py             ConfigError, BackendError, AuthError, WorkspaceError
├── src/                    shared logic
│   ├── __init__.py           get_config(), VERSION, data/config paths
│   ├── projects.py           reads projects.json / env vars
│   └── workspace.py          safe paths, read/search/edit, sections, compile
├── integrations/           how a working copy syncs with the real project
│   ├── __init__.py           build_backend(): picks the integration per project
│   ├── backend.py            Backend contract: ensure_ready, pull, push, status, diff, discard
│   ├── git/client.py         any git remote, or a local folder with no remote
│   └── overleaf/
│       ├── git_bridge.py     Overleaf's official Git bridge (paid plans), compiles on Overleaf when a cookie is set
│       ├── web_client.py     Overleaf web endpoints via session cookie (free plans)
│       ├── socketio.py       read-only joinProject handshake → file/folder ids
│       ├── web_session.py    overleaf-web backend: zip mirror + upload/delete of changed files
│       ├── remote_compile.py compile on Overleaf, download PDF + log (shared by both Overleaf backends)
│       └── browser_login.py  sign in through a real browser window, capture the session over DevTools
├── latex/
│   ├── sections.py           section parsing / replacement (heading commands and levels configurable)
│   ├── includes.py           \input/\include/\subfile/\import tree, sections across files
│   └── compile.py            local latexmk/tectonic compile, log parsing, page count
├── tools/                  MCP tools, one file per area
│   ├── registry.py           registers every module's TOOLS with its annotation
│   ├── project_tools.py      list_projects, list_overleaf_projects, pull, status, diff, push, discard_changes
│   ├── file_tools.py         list/read/search/write/edit/delete/move/import files
│   └── latex_tools.py        outline, read_section, replace_section, compile
├── prompts/                use-case playbooks exposed as MCP prompts
│   ├── loader.py             turns *.md into prompts
│   ├── tailor_resume.md
│   └── edit_document.md
├── scripts/
│   ├── checks/               check.sh: syntax | imports | secrets | all
│   ├── tools/login.py        ./entry.sh login [--paste]: browser sign-in, add a project
│   └── testsuite/            s_flow.py (git), s_web_session.py + fake_overleaf.py, s_multifile.py, s_browser_login.py
└── docs/
```

## Request flow

```
Claude Code ─MCP stdio─▶ app.py ─▶ agent/system.py
                                      │
                    tools/*_tools.py ─┤─ agent/registry.run(project, fn)
                                      ▼
                               src/workspace.py  (local working copy)
                                      │
                               integrations/…    pull / push / diff
                                      ▼
                               Overleaf (Git bridge, or web session)
```

## overleaf-web sync (v0.0.2)

```
Overleaf ──zip download──▶ mirror repo  (~/.local/share/overleaf-mcp/mirrors/<key>, one commit per Overleaf snapshot)
                              ▲   │ git pull --rebase   (a co-author clash stops here)
          git push            │   ▼
          (after upload)    working copy (~/.local/share/overleaf-mcp/workspaces/<key>)
```

On push, the backend takes a fresh snapshot, rebases, then works out `git diff --name-status snapshot..HEAD`. Added and modified files are uploaded (replacing a `.tex` doc goes through Overleaf's own diff, so its history is kept). Deleted files are deleted, and folders left empty are removed. The IDs needed for each call come from one read-only `joinProject` on the editor socket. If something fails part-way, the push reports which files were sent, and the next push sends the rest.

## Design rules

1. **Local first, publish deliberately.** Every edit lands in the working copy. Only `push` touches Overleaf.
2. **Never overwrite a collaborator.** `push` rebases on the remote first; on a conflict it aborts, keeps the local commit, and reports the files.
3. **Secrets never leave projects.json.** The token goes to git as an HTTP header via `GIT_CONFIG_*` env vars: not in `.git/config`, the remote URL, or `ps` output, and it's redacted from error text. `./entry.sh checks secrets` scans the repo for tokens.
4. **Paths stay inside the project.** Absolute paths, `..`, and `.git` are refused.
5. **Generic core, use cases as prompts.** New use case = new markdown file.
6. **Web session is opt-in and light.** It only calls the endpoints the editor itself uses, never writes through the socket, and makes one request per changed file.
7. **Imports at the top of the file.** Enforced by `./entry.sh checks imports`.

## Extending

| To add… | Do this |
| --- | --- |
| A way of reaching Overleaf (e.g. web session for free plans) | New file in `integrations/overleaf/` implementing `integrations/backend.py:Backend`, one branch in `integrations/__init__.py` |
| A tool | Function in the right `tools/<area>_tools.py` and an entry in its `TOOLS` list; new area → new file + add to `tools/registry.py` |
| A use case | `prompts/<name>.md` (shipped) or `~/.config/overleaf-mcp/recipes/<name>.md` (personal) |
| A setting | Key in `config.json`, read with `get_config("<section>")` |
| A rule check | `scripts/checks/check_<name>.py` + a line in `check.sh` |

## Multi-file sections (v0.2.0)

Section tools start from the main file and walk its include tree in document order (`latex/includes.py`). `\input`, `\include` and `\import` resolve from the main file's folder, where TeX runs. `\subfile` and `\subimport` resolve from the file that contains them. Commented-out includes, missing files, cycles and very deep nesting are skipped.

Each section belongs to one file. A section ends at the next heading of the same or higher level, and also just before an include line whose file opens a section of that level. That way, replacing "Summary" in `main.tex` keeps the `\input` that brings in "Experience". An include that only adds body text stays inside its section.

## Roadmap ideas

- PDF page images in compile results, so the layout can be checked visually.
- `\include`-aware search and a flattened read of the whole document.
- Tracked-changes edits through Overleaf's realtime API.
