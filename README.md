# overleaf-mcp v0.2.0

A generic MCP server that connects Claude Code to Overleaf. You describe the change in plain language and Claude reads the LaTeX, edits it, shows you the diff, and saves it back to Overleaf.

First use case: tailoring a resume to a job description. The core doesn't know anything about resumes, though. It edits any LaTeX project, and use cases are added as recipe files.

## How it reaches Overleaf

| Backend | Overleaf plan | How it signs in | Notes |
| --- | --- | --- | --- |
| `overleaf-web` | **Free** or paid | Browser sign-in (`./entry.sh login`) | Uses the same endpoints as the Overleaf web editor. These aren't a public API: they can change without notice, and automating them may go against Overleaf's terms. Keep usage personal and light. The session lasts about 5 days from last use. |
| `overleaf-git` | Paid (Git integration) | Git token | Official and stable. Run `login` too if you want to compile on Overleaf. |
| `git` / `local` | n/a | Optional token | Any git host, or a plain folder. |

Whichever backend you use, edits stay on your machine until you approve a `push`, and a push never overwrites a co-author's change to the same lines.

## Setup (free plan)

```bash
cd ~/overleaf-MCP
./entry.sh setup      # installs deps, creates ~/.config/overleaf-mcp/projects.json (mode 600)
./entry.sh login      # opens a browser: sign in to Overleaf, pick your resume project
./entry.sh register   # adds the server to Claude Code (user scope)
```

`login` opens Chrome, Chromium, Edge or Brave in a separate profile on the Overleaf sign-in page. Sign in the way you normally do (password, Google, SSO). The window closes by itself once you're in. Your password never passes through this tool. `login` then lists your projects, adds the one you pick, and saves the session to `projects.json` (mode 600). When the session expires (about 5 days after last use), tools say so; run `./entry.sh login` again, which is usually one click.

**Using VS Code Remote-SSH, or any SSH session?** A browser window would open on the remote machine's screen, so `login` switches to paste mode automatically and prints these steps. Sign in to Overleaf in the browser on **your own computer**, press F12, go to **Application** (Firefox: **Storage**) → **Cookies** → `https://www.overleaf.com`, and copy the **Value** of `overleaf_session2` (it starts with `s%3A`). Paste it into the VS Code terminal and press Enter; nothing shows while you paste. You can force either mode with `--paste` or `--browser`.

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
| `list_files`, `read_file`, `search` | Read only |
| `outline`, `read_section` | Read only. Follow `\input` / `\include` / `\subfile` / `\import` from the main file, so templates with one file per section work. |
| `write_file`, `edit_file`, `replace_section`, `move_file`, `import_file` | Change the local copy only (`replace_section` edits whichever file holds the section) |
| `delete_file`, `discard_changes` | Destructive, local copy only |
| `compile` | `where=overleaf`: Overleaf builds what is pushed, and the PDF and log are downloaded. `where=local`: latexmk/tectonic on this machine, including unpushed edits. `auto` uses local if TeX is installed. Both report errors, warnings and the number of `pages`. |
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
