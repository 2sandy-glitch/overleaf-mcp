---
name: tailor_resume
description: Tailor a LaTeX resume on Overleaf to a job description, then push it
arguments: job_description, project, notes
---
You are editing a LaTeX resume that lives in the Overleaf project "{project}" (empty means the default project), using the overleaf MCP tools.

Job description / target role:
<job_description>
{job_description}
</job_description>

Extra instructions from me:
<notes>
{notes}
</notes>

Do this:
1. `pull` the project, then `outline` the main file and read every section that matters (summary, experience, projects, skills, education).
2. Plan the changes: lead with the experience and skills this role asks for, reuse the job description's own wording where it is truthful, and cut or shorten what is irrelevant. Never invent employers, dates, titles, degrees, numbers, or skills I do not already list or mention in my notes.
3. Make the edits with `replace_section` or `edit_file`. Keep the template's own macros and structure; escape LaTeX special characters (& % $ # _ { } ~ ^ \).
4. Keep it to the same page count as before unless I said otherwise.
5. Run `compile` if a local compiler is available and fix any errors it reports.
6. Show me the `diff` and a short summary of what changed and why. Push only after I say yes, with a commit message naming the role.
