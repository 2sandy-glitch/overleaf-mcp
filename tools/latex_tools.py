"""LaTeX tools: work by section heading, and compile locally."""

from agent.registry import run


def outline(project: str | None = None, path: str | None = None) -> list[dict]:
    """List section headings with file, level and line span. Default: the main
    file and every file it pulls in with \\input / \\include / \\subfile / \\import,
    in document order. Give `path` to look at one file only."""
    return run(project, lambda ws: ws.outline(path))


def read_section(title: str, project: str | None = None, path: str | None = None) -> dict:
    """Read one section, heading line included, by its title. Searches the main
    file and its included files unless `path` is given."""
    return run(project, lambda ws: ws.read_section(path, title))


def replace_section(title: str, content: str, project: str | None = None, path: str | None = None) -> dict:
    """Replace one whole section (heading line included) with `content`, in
    whichever file holds it. Include the heading command in `content` to keep it."""
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
