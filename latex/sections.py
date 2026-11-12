"""Find and replace LaTeX sections by heading.

A section runs from its heading line up to the next heading of the same or a
higher level (or the end of the document body). Which commands count as
headings is configurable per project, so resume templates with custom
commands (e.g. \\cvsection) work the same as articles.
"""


import re
from dataclasses import dataclass


@dataclass
class Section:
    command: str
    level: int
    title: str
    start_line: int  # 1-based, the heading line
    end_line: int  # 1-based, inclusive
    path: str = ""  # file the section lives in (multi-file projects)

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "command": self.command,
            "level": self.level,
            "title": self.title,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


def levels(commands: list) -> dict[str, int]:
    """Heading command -> level. Each entry is one level: a name, or a list of names
    that rank the same (e.g. ["section", "cvsection"])."""
    out: dict[str, int] = {}
    for i, item in enumerate(commands):
        for name in [item] if isinstance(item, str) else item:
            out[name] = i
    return out


def _heading_regex(commands: list) -> re.Pattern:
    names = "|".join(re.escape(c) for c in sorted(levels(commands), key=len, reverse=True))
    # \section*[short]{Title}  — title may contain one level of nested braces.
    return re.compile(r"^[ \t]*\\(" + names + r")\*?(?:\[[^\]]*\])?\{((?:[^{}]|\{[^{}]*\})*)\}")


def _strip_comment(line: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", line)


def parse_sections(text: str, commands: list, path: str = "") -> list[Section]:
    pattern = _heading_regex(commands)
    level_of = levels(commands)
    lines = text.splitlines()

    # Sections never run past \end{document}.
    body_end = len(lines)
    for i, line in enumerate(lines):
        if re.match(r"^\s*\\end\{document\}", line):
            body_end = i
            break

    found: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines[:body_end]):
        m = pattern.match(_strip_comment(line))
        if m:
            found.append((i, m.group(1), m.group(2).strip()))

    sections: list[Section] = []
    for idx, (line_no, cmd, title) in enumerate(found):
        level = level_of[cmd]
        end = body_end
        for next_line, next_cmd, _ in found[idx + 1 :]:
            if level_of[next_cmd] <= level:
                end = next_line
                break
        # Trim trailing blank lines from the section span.
        while end - 1 > line_no and not lines[end - 1].strip():
            end -= 1
        sections.append(Section(cmd, level, title, line_no + 1, end, path))
    return sections


def find_section(sections: list[Section], title: str) -> Section:
    exact = [s for s in sections if s.title == title]
    if len(exact) == 1:
        return exact[0]
    loose = [s for s in sections if s.title.lower().strip() == title.lower().strip()]
    if len(loose) == 1:
        return loose[0]
    if len(exact) > 1 or len(loose) > 1:
        where = ", ".join(f"{s.path}:{s.start_line}" if s.path else str(s.start_line) for s in (exact or loose))
        raise ValueError(f"Several sections are titled '{title}' ({where}); pass path, or edit by text instead.")
    known = "; ".join(s.title for s in sections) or "none found"
    raise ValueError(f"No section titled '{title}'. Sections: {known}")


def section_text(text: str, section: Section) -> str:
    lines = text.splitlines()
    return "\n".join(lines[section.start_line - 1 : section.end_line])


def replace_section(text: str, section: Section, new_content: str) -> str:
    lines = text.splitlines()
    trailing_newline = text.endswith("\n")
    new_lines = new_content.rstrip("\n").splitlines()
    out = lines[: section.start_line - 1] + new_lines + lines[section.end_line :]
    return "\n".join(out) + ("\n" if trailing_newline else "")
