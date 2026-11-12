# overleaf-mcp v0.0.2

A generic MCP server that connects Claude Code to Overleaf. You describe the change in plain language and Claude reads the LaTeX, edits it, shows you the diff, and saves it back to Overleaf.

First use case: tailoring a resume to a job description. The core doesn't know anything about resumes, though. It edits any LaTeX project, and use cases are added as recipe files.

## How it reaches Overleaf

| Backend | Overleaf plan | How it signs in | Notes |
| --- | --- | --- | --- |
| `overleaf-web` (new in 0.0.2) | **Free** or paid | Your browser session cookie | Uses the same endpoints as the Overleaf web editor. These aren't a public API: they can change without notice, and automating them may go against Overleaf's terms. Keep usage personal and light. The session lasts about 5 days from last use. |
| `overleaf-git` | Paid (Git integration) | Git token | Official and stable. |
| `git` / `local` | n/a | Optional token | Any git host, or a plain folder. |

Whichever backend you use, edits stay on your machine until you approve a `push`, and a push never overwrites a co-author's change to the same lines.

## Setup (free plan)

```bash
cd ~/overleaf-MCP
./entry.sh setup      # installs deps, creates ~/.config/overleaf-mcp/projects.json (mode 600)
./entry.sh login      # paste your Overleaf session cookie, pick your resume project
./entry.sh register   # adds the server to Claude Code (user scope)
```

**Getting the cookie for `login`.** Overleaf's sign-in page has a captcha, so the tool never asks for your password:

1. Sign in at overleaf.com in your browser.
2. Open DevTools (F12) → **Application** (Chrome) or **Storage** (Firefox) → **Cookies** → `https://www.overleaf.com`.
3. Copy the **Value** of `overleaf_session2` and paste it at the hidden prompt.

`login` checks the cookie, lists your projects, adds the one you pick, and saves everything to `projects.json` (mode 600). When the session expires, tools say so; run `./entry.sh login` again.

Restart Claude Code and check `/mcp`. `overleaf` should be listed as connected. `./entry.sh status` shows the version, the projects file, and the registration.

For the paid Git bridge, another git host, or a local folder, add entries by hand following [projects.example.json](projects.example.json).

## Using it

Plain language:

> Pull my resume, tailor it to this job description: … Show me the diff, compile it on Overleaf, and push when I say yes.

Or the built-in recipe, which shows up as a slash command:

```
/mcp__overleaf__tailor_resume
```

The usual flow: `pull` → `outline` / `read_section` → `replace_section` / `edit_file` → `diff` → you approve → `push` → `compile` (on Overleaf, which downloads the PDF).

## Tools

| Tool | Effect |
| --- | --- |
| `list_projects`, `status`, `diff` | Read only |
| `list_overleaf_projects` | Read only: projects in your Overleaf account (needs `login`) |
| `pull` | Fetch the latest from Overleaf, keeping local edits |
| `list_files`, `read_file`, `search`, `outline`, `read_section` | Read only |
| `write_file`, `edit_file`, `replace_section`, `move_file`, `import_file` | Change the local copy only |
| `delete_file`, `discard_changes` | Destructive, local copy only |
| `compile` | `where=overleaf`: Overleaf builds what is pushed, and the PDF and log are downloaded. `where=local`: latexmk/tectonic on this machine, including unpushed edits. `auto` uses local if TeX is installed. |
| `push` | Publish to Overleaf. Refuses if a co-author changed the same lines |

Working copies live in `~/.local/share/overleaf-mcp/workspaces/<project>/`, and compile output in `~/.local/share/overleaf-mcp/builds/<project>/`.

## Your own recipes

Put `<name>.md` in `~/.config/overleaf-mcp/recipes/`. It needs frontmatter with `name`, `description` and `arguments`, and a body that uses `{argument}` placeholders. Copy `prompts/tailor_resume.md` as a starting point. Restart Claude Code to load it.

## Code layout

Flat folders by role, like the ACI agentic-system: `app.py`, `entry.sh`, `config.json`, `agent/`, `src/`, `integrations/`, `latex/`, `tools/`, `prompts/`, `scripts/`. The full map and how to extend each part are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Changes per version are in [CHANGELOG.md](CHANGELOG.md).

## Development

```bash
./entry.sh testsuite   # end-to-end tests (fake Overleaf + bare git repo)
./entry.sh checks      # syntax, imports-at-top, no committed tokens
```
