# Changelog

## 0.2.0 (2026-11-12)

- **Browser login.** `./entry.sh login` opens Chrome, Chromium, Edge or Brave with a separate profile on the Overleaf sign-in page. You sign in as usual (password, Google, SSO, captcha, 2FA) and the window closes by itself once the session works. The password never passes through overleaf-mcp. The profile is kept, so signing in again is usually one click. `--paste` keeps the old copy-the-cookie flow.
- **Multi-file projects.** `outline`, `read_section` and `replace_section` follow `\input`, `\include`, `\subfile` and `\import`/`\subimport` from the main file, in document order, and edit the file that holds the section. A section stops before an include that opens its own section, so replacing one section never removes the `\input` lines for the next.
- **Heading levels.** `section_commands` can group commands of equal rank. The default ranks `\cvsection` with `\section` and `\cvsubsection` with `\subsection`.
- **Page count.** Both compile modes report `pages`, read from the TeX log or counted in the PDF, so "keep it to one page" can be checked.
- **Compile on Overleaf for Git-bridge projects** when a session cookie is also saved. Compile results include the main file that was built and never report a PDF left over from an earlier build.
- 9 new tests: multi-file sections, include resolution, page counts, Git-bridge remote compile, and browser login against a real headless Chrome.

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
