---
name: edit_document
description: Apply a plain-language change request to any LaTeX project on Overleaf
arguments: instruction, project
---
Using the overleaf MCP tools, change the Overleaf project "{project}" (empty means the default project) as follows:

<instruction>
{instruction}
</instruction>

Steps: `pull` first; use `outline`, `search` and `read_file` to find the right place; edit with `replace_section` or `edit_file` (keep existing macros and preamble unless asked); `compile` if a local compiler is available and fix errors; show the `diff` and a short summary. Push only after I confirm.
