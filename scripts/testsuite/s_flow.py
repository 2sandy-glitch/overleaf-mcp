"""End-to-end flow against a bare git repo standing in for Overleaf's git bridge."""

import json
import os
import subprocess
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent import registry
from agent.errors import WorkspaceError
from integrations.overleaf.git_bridge import overleaf_git_backend
from latex.sections import parse_sections

ROOT = Path(__file__).resolve().parents[2]

RESUME = r"""\documentclass{article}
\begin{document}
\section{Summary}
Backend engineer.

\section{Experience}
\subsection{Acme}
Built APIs.

\section{Skills}
Python, Django
\end{document}
"""


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def remote(tmp_path, monkeypatch):
    bare = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "master", str(bare), cwd=tmp_path)
    seed = tmp_path / "seed"
    git("clone", "-q", str(bare), str(seed), cwd=tmp_path)
    (seed / "main.tex").write_text(RESUME)
    git("add", "-A", cwd=seed)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init", cwd=seed)
    git("push", "-q", "origin", "master", cwd=seed)

    cfg = tmp_path / "projects.json"
    cfg.write_text(json.dumps({"default": "cv", "projects": {"cv": {"backend": "git", "remote_url": str(bare)}}}))
    monkeypatch.setenv("OVERLEAF_MCP_CONFIG", str(cfg))
    monkeypatch.setenv("OVERLEAF_MCP_HOME", str(tmp_path / "home"))
    for var in ("OVERLEAF_PROJECT_ID", "OVERLEAF_GIT_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    registry.reset()
    return {"bare": bare, "seed": seed}


def test_sections_and_spans():
    s = parse_sections(RESUME, ["section", "subsection"])
    assert [x.title for x in s] == ["Summary", "Experience", "Acme", "Skills"]
    exp = s[1]
    assert (exp.start_line, exp.end_line) == (6, 8)
    assert s[3].end_line == 11  # stops before \end{document}


def test_edit_push_and_conflict(remote):
    ws = registry.workspace(None)
    assert ws.backend.pull().ok

    ws.replace_section(None, "Skills", "\\section{Skills}\nPython, Django, LaTeX")
    assert "LaTeX" in ws.backend.diff()
    res = ws.backend.push("Add LaTeX skill")
    assert res.ok, res.message

    seed = remote["seed"]
    git("pull", "-q", cwd=seed)
    assert "LaTeX" in (seed / "main.tex").read_text()

    # Collaborator edits the same line on "Overleaf"; our push must refuse.
    text = (seed / "main.tex").read_text().replace("Backend engineer.", "Senior backend engineer.")
    (seed / "main.tex").write_text(text)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "co-author", cwd=seed)
    git("push", "-q", "origin", "master", cwd=seed)

    ws.edit("main.tex", "Backend engineer.", "Platform engineer.")
    res = ws.backend.push("conflicting")
    assert not res.ok and res.conflicts == ["main.tex"]
    assert "Senior" not in ws.read("main.tex")  # nothing silently merged


def test_path_escape_blocked(remote):
    ws = registry.workspace(None)
    for bad in ("../x.tex", "/etc/passwd", ".git/config"):
        with pytest.raises(WorkspaceError):
            ws.write(bad, "x")


def test_token_not_in_git_config(tmp_path, monkeypatch):
    b = overleaf_git_backend(tmp_path / "w", "abc123", "olp_SECRET", "https://git.example.invalid")
    env = b._env()
    assert "olp_SECRET" not in b.remote_url
    assert env["GIT_CONFIG_KEY_0"] == "http.extraHeader"
    assert b._redact("fatal olp_SECRET") == "fatal ***"


def test_mcp_stdio_roundtrip(remote):
    """Talk to the real server process over MCP stdio."""
    async def go():
        params = StdioServerParameters(
            command="uv", args=["run", "-q", "--directory", str(ROOT), "python", "app.py"], env=dict(os.environ)
        )
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = {t.name for t in (await s.list_tools()).tools}
                assert {"pull", "outline", "replace_section", "push", "diff"} <= tools
                prompts = {p.name for p in (await s.list_prompts()).prompts}
                assert "tailor_resume" in prompts
                await s.call_tool("pull", {})
                out = await s.call_tool("outline", {})
                assert "Experience" in str(out.content)
                p = await s.get_prompt("tailor_resume", {"job_description": "Staff SRE"})
                assert "Staff SRE" in str(p.messages[0].content)

    anyio.run(go)
