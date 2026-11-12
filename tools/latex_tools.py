"""LaTeX tools: work by section heading, and compile locally."""

from agent.registry import run


def outline(project: str | None = None, path: str | None = None) -> list[dict]:
    """List the section headings of a .tex file (default: the main file)
    with level and line span."""
    return run(project, lambda ws: ws.outline(path))


def read_section(title: str, project: str | None = None, path: str | None = None) -> dict:
    """Read one section, heading line included, by its title."""
    return run(project, lambda ws: ws.read_section(path, title))


def replace_section(title: str, content: str, project: str | None = None, path: str | None = None) -> dict:
    """Replace one whole section (heading line included) with `content`.
    Include the heading command in `content` if you want to keep it."""
    return run(project, lambda ws: ws.replace_section(path, title, content))


def compile(
    project: str | None = None, main_file: str | None = None, engine: str | None = None, where: str = "auto"
) -> dict:
    """Compile and report errors with file and line, plus the PDF path.
    where: local (latexmk/tectonic on this machine, includes unpushed edits),
    overleaf (Overleaf builds what is pushed; overleaf-web projects), auto (local if TeX is installed).
    engine (local only): pdflatex, xelatex or lualatex."""
    return run(project, lambda ws: ws.compile(main_file, engine, where))


TOOLS = [
    (outline, "read"),
    (read_section, "read"),
    (replace_section, "write"),
    (compile, "write"),
]
