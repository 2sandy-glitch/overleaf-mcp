"""overleaf-web backend against the fake Overleaf: pull, push, conflicts, folders, compile, auth."""

import json
import subprocess

import pytest
from fake_overleaf import COOKIE, PROJECT_ID, FakeOverleaf

from agent import registry
from agent.errors import AuthError, WorkspaceError
from integrations.overleaf import socketio, web_client

RESUME = b"""\\documentclass{article}
\\begin{document}
\\section{Summary}
Backend engineer.

\\section{Skills}
Python, Django
\\end{document}
"""


@pytest.fixture
def fake(tmp_path, monkeypatch):
    ov = FakeOverleaf({"main.tex": RESUME, "photo.png": b"\x89PNG fake"})
    monkeypatch.setattr(web_client, "default_transport", ov.transport())
    monkeypatch.setattr(socketio, "join_project", ov.join_project)
    cfg = tmp_path / "projects.json"
    cfg.write_text(
        json.dumps(
            {
                "default": "cv",
                "overleaf_cookie": f"overleaf_session2={COOKIE}",
                "projects": {"cv": {"backend": "overleaf-web", "project_id": PROJECT_ID}},
            }
        )
    )
    monkeypatch.setenv("OVERLEAF_MCP_CONFIG", str(cfg))
    monkeypatch.setenv("OVERLEAF_MCP_HOME", str(tmp_path / "home"))
    for var in ("OVERLEAF_PROJECT_ID", "OVERLEAF_GIT_TOKEN", "OVERLEAF_COOKIE"):
        monkeypatch.delenv(var, raising=False)
    registry.reset()
    return ov


def test_pull_edit_push_uploads_only_changes(fake):
    ws = registry.workspace(None)
    assert ws.backend.pull().ok
    assert ws.read("main.tex") == RESUME.decode()

    ws.replace_section(None, "Skills", "\\section{Skills}\nPython, Django, LaTeX")
    res = ws.backend.push("Add LaTeX")
    assert res.ok, res.message
    assert res.changed_files == ["main.tex"]
    assert b"LaTeX" in fake.files["main.tex"]
    uploads = [c for c in fake.calls if c.endswith("/upload")]
    assert len(uploads) == 1  # photo.png untouched
    assert ws.backend.diff() == ""


def test_push_refuses_on_coauthor_conflict(fake):
    ws = registry.workspace(None)
    ws.backend.pull()
    fake.files["main.tex"] = RESUME.replace(b"Backend engineer.", b"Senior backend engineer.")
    ws.edit("main.tex", "Backend engineer.", "Platform engineer.")

    res = ws.backend.push("conflicting")
    assert not res.ok and res.conflicts == ["main.tex"]
    assert b"Senior" in fake.files["main.tex"]  # co-author's text kept on Overleaf
    assert not [c for c in fake.calls if c.endswith("/upload")]


def test_coauthor_change_elsewhere_merges(fake):
    ws = registry.workspace(None)
    ws.backend.pull()
    fake.files["refs.bib"] = b"@book{x, title={X}}"
    fake._register("refs.bib")
    ws.edit("main.tex", "Python, Django", "Python, Django, Go")

    res = ws.backend.push("Add Go")
    assert res.ok, res.message
    assert (ws.root / "refs.bib").exists()
    assert b"Go" in fake.files["main.tex"]
    assert fake.files["refs.bib"] == b"@book{x, title={X}}"


def test_new_folder_and_delete(fake):
    ws = registry.workspace(None)
    ws.backend.pull()
    ws.write("sections/extra.tex", "\\section{Extra}\n")
    ws.delete("photo.png")

    res = ws.backend.push("restructure")
    assert res.ok, res.message
    assert "sections" in fake.folders
    assert fake.files["sections/extra.tex"] == b"\\section{Extra}\n"
    assert "photo.png" not in fake.files

    ws.delete("sections/extra.tex")
    assert ws.backend.push("remove extra").ok
    assert "sections" not in fake.folders  # emptied folder removed on Overleaf too


def test_remote_compile_downloads_pdf(fake):
    ws = registry.workspace(None)
    out = ws.compile(where="overleaf")
    assert out["ok"] and out["compiler"] == "overleaf"
    assert open(out["pdf"], "rb").read().startswith(b"%PDF")
    assert out["warnings"] == ["LaTeX Warning: fake warning"]


def test_expired_session_is_explained(fake):
    fake.signed_in = False
    ws = registry.workspace(None)
    with pytest.raises(AuthError, match="entry.sh login"):
        ws.backend.pull()


def test_cookie_and_packet_parsing():
    assert web_client.parse_cookie("abc") == {"overleaf_session2": "abc"}
    assert web_client.parse_cookie("Cookie: a=1; b=2") == {"a": "1", "b": "2"}
    assert socketio.parse_handshake("sid1:60:60:websocket,xhr-polling") == ("sid1", ["websocket", "xhr-polling"])
    assert socketio.parse_event('5:::{"name":"joinProjectResponse","args":[{"project":{}}]}') == (
        "joinProjectResponse",
        [{"project": {}}],
    )
    assert socketio.parse_event("2::") is None
    tree = socketio.flatten_tree(
        [{"_id": "r", "docs": [{"_id": "d", "name": "main.tex"}], "folders": [{"_id": "f", "name": "img", "fileRefs": [{"_id": "x", "name": "a.png"}]}]}]
    )
    assert tree == {
        "": {"id": "r", "type": "folder"},
        "main.tex": {"id": "d", "type": "doc"},
        "img": {"id": "f", "type": "folder"},
        "img/a.png": {"id": "x", "type": "file"},
    }


def test_git_bridge_project_compiles_on_overleaf_with_cookie(fake, tmp_path, monkeypatch):
    hosts = tmp_path / "githost"
    seed = tmp_path / "seed"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(hosts / PROJECT_ID)], check=True)
    subprocess.run(["git", "clone", "-q", str(hosts / PROJECT_ID), str(seed)], check=True, capture_output=True)
    (seed / "main.tex").write_bytes(RESUME)
    for args in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], ["push", "-q", "origin", "master"]):
        subprocess.run(["git", *args], cwd=seed, check=True, capture_output=True)

    cfg = tmp_path / "projects.json"
    project = {"backend": "overleaf-git", "project_id": PROJECT_ID, "token": "t0k", "git_host": str(hosts)}
    cfg.write_text(json.dumps({"default": "g", "overleaf_cookie": f"overleaf_session2={COOKIE}", "projects": {"g": project}}))
    registry.reset()
    ws = registry.workspace(None)
    out = ws.compile(where="overleaf")
    assert out["ok"] and out["pdf"] and out["note"] == ""

    cfg.write_text(json.dumps({"default": "g", "projects": {"g": project}}))  # no cookie -> clear refusal
    with pytest.raises(WorkspaceError, match="session cookie"):
        registry.workspace(None).compile(where="overleaf")
