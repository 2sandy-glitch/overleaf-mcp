"""Follow \\input / \\include / \\subfile / \\import across a project.

Many templates (resumes especially) keep each section in its own file. This
walks the include tree from the main file in document order so section tools
can work across all of them.
"""

import posixpath
import re
from pathlib import PurePosixPath

from latex.sections import Section, parse_sections

MAX_DEPTH = 12

# \input{x}  \include{x}  \subfile{x}  \import{dir/}{x}  \subimport{dir/}{x}  \includefrom / \inputfrom too
_SIMPLE = re.compile(r"\\(input|include|subfile)\s*\{([^}]+)\}")
_IMPORT = re.compile(r"\\(import|subimport|inputfrom|subinputfrom|includefrom|subincludefrom)\*?\s*\{([^}]*)\}\s*\{([^}]+)\}")
_COMMENT = re.compile(r"(?<!\\)%.*")


def _candidates(name: str) -> list[str]:
    name = name.strip()
    return [name] if name.endswith(".tex") else [f"{name}.tex", name]


def _norm(path: str) -> str:
    return posixpath.normpath(path).lstrip("/") if path else path


def include_lines(text: str, current_file: str, main_dir: str = "") -> list[tuple[int, str]]:
    """(1-based line, project-relative target) for each include, in order (targets not checked to exist).

    \\input / \\include / \\import resolve from the main file's folder (where TeX runs);
    \\subfile / \\subimport resolve from the file that contains them.
    """
    here = str(PurePosixPath(current_file).parent)
    found: list[tuple[int, int, str]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = _COMMENT.sub("", line)
        for m in _SIMPLE.finditer(line):
            base = here if m.group(1) == "subfile" else main_dir
            found.append((lineno, m.start(), _norm(posixpath.join(base or ".", m.group(2).strip()))))
        for m in _IMPORT.finditer(line):
            base = here if m.group(1).startswith("sub") else main_dir
            found.append((lineno, m.start(), _norm(posixpath.join(base or ".", m.group(2).strip(), m.group(3).strip()))))
    return [(ln, target) for ln, _, target in sorted(found)]


def find_includes(text: str, current_file: str, main_dir: str = "") -> list[str]:
    return [target for _, target in include_lines(text, current_file, main_dir)]


def _resolve(target: str, read) -> str | None:
    for cand in _candidates(target):
        norm = _norm(cand)
        if read(norm) is not None:
            return norm
    return None


def include_tree(main_file: str, read) -> list[str]:
    """Files reachable from main_file, main first, in document order.

    ``read(path)`` returns the file's text or None if it does not exist.
    Missing files are skipped; cycles and very deep nesting are cut off.
    """
    order: list[str] = []
    seen: set[str] = set()
    main_dir = str(PurePosixPath(main_file).parent)
    main_dir = "" if main_dir == "." else main_dir

    def visit(path: str, depth: int) -> None:
        if path in seen or depth > MAX_DEPTH:
            return
        text = read(path)
        if text is None:
            return
        seen.add(path)
        order.append(path)
        for target in find_includes(text, path, main_dir):
            resolved = _resolve(target, read)
            if resolved is not None:
                visit(resolved, depth + 1)

    visit(main_file, 0)
    return order


def document_sections(root_file: str, read, commands: list) -> list[Section]:
    """Sections of root_file and every file it pulls in, in document order.

    A section stops before an include line whose file opens a section of the
    same or higher level, so replacing "Summary" in main.tex never swallows
    the \\input that brings in "Experience". An \\input that only adds body
    text (no heading of that level) stays part of the section.
    """
    files = include_tree(root_file, read)
    main_dir = str(PurePosixPath(root_file).parent)
    main_dir = "" if main_dir == "." else main_dir
    secs = {f: parse_sections(read(f), commands, f) for f in files}
    children = {
        f: [(ln, r) for ln, t in include_lines(read(f), f, main_dir) if (r := _resolve(t, read)) in secs]
        for f in files
    }

    top: dict[str, int | None] = {}

    def top_level(f: str, stack: frozenset = frozenset()) -> int | None:
        """Highest (smallest-number) heading level in f and everything it includes."""
        if f in top:
            return top[f]
        levels = [s.level for s in secs[f]]
        for _, child in children[f]:
            if child not in stack:
                lvl = top_level(child, stack | {f})
                if lvl is not None:
                    levels.append(lvl)
        top[f] = min(levels) if levels else None
        return top[f]

    lines_of = {f: read(f).splitlines() for f in files}
    for f in files:
        for s in secs[f]:
            for ln, child in children[f]:
                lvl = top_level(child)
                if s.start_line < ln <= s.end_line and lvl is not None and lvl <= s.level:
                    end = ln - 1
                    while end > s.start_line and not lines_of[f][end - 1].strip():
                        end -= 1
                    s.end_line = end
                    break
    return [s for f in files for s in secs[f]]
