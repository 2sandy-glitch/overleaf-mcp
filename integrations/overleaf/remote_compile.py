"""Compile on Overleaf's servers and download the PDF and log.

Shared by both Overleaf backends: overleaf-web always, and overleaf-git when a
session cookie is also configured. Overleaf compiles its own copy of the
project, so local edits that are not pushed yet are not in the PDF.
"""

from pathlib import Path

from agent.errors import BackendError
from latex.compile import page_count, parse_log

OUTPUTS = ("output.pdf", "output.log")


def compile_on_overleaf(client, project_id: str, main_file: str, out_dir: Path) -> dict:
    tree, project = client.tree(project_id)
    root_path = main_file
    entity = tree.get(root_path)
    if entity is not None and entity["type"] == "doc":
        root_id = entity["id"]
    else:
        root_id = project.get("rootDoc_id")
        if not root_id:
            raise BackendError(f"'{main_file}' is not a document on Overleaf and the project has no main document set.")
        root_path = next((p for p, e in tree.items() if e["id"] == root_id), main_file)

    result = client.compile(project_id, root_id, root_path)
    status = result.get("status", "unknown")
    outputs = {f.get("path"): f for f in result.get("outputFiles") or []}

    out_dir.mkdir(parents=True, exist_ok=True)
    for name in OUTPUTS:  # never report a stale PDF from an earlier build
        (out_dir / name).unlink(missing_ok=True)
    saved = {}
    for name in OUTPUTS:
        if name in outputs and outputs[name].get("url"):
            (out_dir / name).write_bytes(client.fetch_output(outputs[name]["url"], result.get("clsiServerId")))
            saved[name] = out_dir / name

    log = saved["output.log"].read_text(errors="replace") if "output.log" in saved else ""
    return {
        "ok": status == "success",
        "compiler": "overleaf",
        "status": status,
        "main_file": root_path,
        "pdf": str(saved["output.pdf"]) if "output.pdf" in saved else None,
        "pages": page_count(log, saved.get("output.pdf")),
        "log": str(saved["output.log"]) if "output.log" in saved else None,
        "message": "Compiled on Overleaf." if status == "success" else f"Overleaf compile status: {status}.",
        **parse_log(log),
    }


def unpushed_note(status: dict) -> str:
    pending = len(status.get("uncommitted_changes") or []) + int(status.get("unpushed_commits") or 0)
    return "Overleaf compiled its own copy; unpushed local edits are not included." if pending else ""
