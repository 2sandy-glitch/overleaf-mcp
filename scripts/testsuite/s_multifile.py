"""Sections across \\input / \\include files."""

import json

import pytest

from agent import registry
from agent.errors import WorkspaceError
from latex.includes import find_includes, include_tree

MAIN = r"""\documentclass{article}
\begin{document}
\section{Summary}
Engineer.
\input{sections/experience}
% \input{sections/old}
\include{sections/skills}
\end{document}
"""
EXPERIENCE = r"""\cvsection{Experience}
\cvsubsection{Acme}
Built APIs.
"""
SKILLS = r"""\section{Skills}
Python
"""


@pytest.fixture
def ws(tmp_path, monkeypatch):
    proj = tmp_path / "cv"
    (proj / "sections").mkdir(parents=True)
    (proj / "main.tex").write_text(MAIN)
    (proj / "sections/experience.tex").write_text(EXPERIENCE)
    (proj / "sections/skills.tex").write_text(SKILLS)
    (proj / "sections/old.tex").write_text("\\section{Old}\n")
    cfg = tmp_path / "projects.json"
    cfg.write_text(json.dumps({"default": "cv", "projects": {"cv": {"backend": "local", "path": str(proj)}}}))
    monkeypatch.setenv("OVERLEAF_MCP_CONFIG", str(cfg))
    monkeypatch.setenv("OVERLEAF_MCP_HOME", str(tmp_path / "home"))
    for var in ("OVERLEAF_PROJECT_ID", "OVERLEAF_GIT_TOKEN", "OVERLEAF_COOKIE"):
        monkeypatch.delenv(var, raising=False)
    registry.reset()
    return registry.workspace(None)


def test_outline_follows_includes_in_order(ws):
    out = ws.outline()
    assert [(s["path"], s["title"]) for s in out] == [
        ("main.tex", "Summary"),
        ("sections/experience.tex", "Experience"),
        ("sections/experience.tex", "Acme"),
        ("sections/skills.tex", "Skills"),
    ]  # commented-out \input skipped


def test_read_and_replace_in_included_file(ws):
    sec = ws.read_section(None, "Experience")
    assert sec["path"] == "sections/experience.tex" and "Built APIs." in sec["content"]

    res = ws.replace_section(None, "Skills", "\\section{Skills}\nPython, LaTeX")
    assert res["path"] == "sections/skills.tex"
    assert "LaTeX" in ws.read("sections/skills.tex")
    assert ws.read("main.tex") == MAIN


def test_single_file_and_ambiguity(ws):
    assert [s["title"] for s in ws.outline("sections/old.tex")] == ["Old"]
    ws.write("sections/skills.tex", SKILLS + "\\section{Summary}\nDup\n")
    with pytest.raises(WorkspaceError, match="main.tex:3, sections/skills.tex"):
        ws.read_section(None, "Summary")
    assert ws.read_section("main.tex", "Summary")["content"].endswith("Engineer.")


def test_include_resolution_rules():
    text = "\\input{a}\n\\subimport{parts/}{b}\n\\import{x/}{c.tex}\n\\subfile{../d}"
    assert find_includes(text, "cv/sub/main.tex", "cv") == ["cv/a", "cv/sub/parts/b", "cv/x/c.tex", "cv/d"]
    files = {"main.tex": "\\input{a}\\input{main}", "a.tex": "\\input{a}"}
    assert include_tree("main.tex", files.get) == ["main.tex", "a.tex"]  # cycles cut

