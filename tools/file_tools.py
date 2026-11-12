"""File tools: read, search and change files in the local working copy."""

from agent.registry import run


def list_files(project: str | None = None, pattern: str = "*") -> list[dict]:
    """List files in the project. `pattern` is a glob such as '*.tex' or 'figures/*'."""
    return run(project, lambda ws: ws.list_files(pattern))


def read_file(path: str, project: str | None = None, start_line: int | None = None, end_line: int | None = None) -> str:
    """Read a text file. Give start_line/end_line to get a numbered slice."""
    return run(project, lambda ws: ws.read(path, start_line, end_line))


def search(query: str, project: str | None = None, regex: bool = False, pattern: str = "*.tex") -> list[dict]:
    """Case-insensitive search across project files; returns path, line, text."""
    return run(project, lambda ws: ws.search(query, regex, pattern))


def write_file(path: str, content: str, project: str | None = None) -> dict:
    """Create or fully overwrite a file in the working copy. Prefer edit_file
    or replace_section for changes to existing files."""
    return run(project, lambda ws: ws.write(path, content))


def edit_file(path: str, old_text: str, new_text: str, project: str | None = None, replace_all: bool = False) -> dict:
    """Replace an exact piece of text. `old_text` must match exactly once
    unless replace_all is set."""
    return run(project, lambda ws: ws.edit(path, old_text, new_text, replace_all))


def delete_file(path: str, project: str | None = None) -> dict:
    """Delete a file or folder from the working copy (removed on Overleaf at next push)."""
    return run(project, lambda ws: ws.delete(path))


def move_file(source: str, destination: str, project: str | None = None) -> dict:
    """Rename or move a file inside the project."""
    return run(project, lambda ws: ws.move(source, destination))


def import_file(local_path: str, destination: str, project: str | None = None) -> dict:
    """Copy a file from this computer (e.g. a photo or .bib) into the project."""
    return run(project, lambda ws: ws.import_file(local_path, destination))


TOOLS = [
    (list_files, "read"),
    (read_file, "read"),
    (search, "read"),
    (write_file, "write"),
    (edit_file, "write"),
    (delete_file, "destructive"),
    (move_file, "write"),
    (import_file, "write"),
]
