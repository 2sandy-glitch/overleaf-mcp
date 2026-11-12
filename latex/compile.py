"""Optional local compile, to catch LaTeX errors before pushing.

Uses latexmk if installed, else tectonic. Output goes to a separate build
folder so the project working copy (and the next push) stays clean.
Overleaf itself always recompiles after a push; this is just an early check.
"""

import re
import shutil
import subprocess
from pathlib import Path

from src import get_config

ENGINE_FLAGS = {"pdflatex": "-pdf", "xelatex": "-xelatex", "lualatex": "-lualatex"}


def available_compiler() -> str | None:
    for tool in ("latexmk", "tectonic"):
        if shutil.which(tool):
            return tool
    return None


def parse_log(log: str) -> dict:
    errors, warnings = [], []
    lines = log.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(.*?\.tex):(\d+): (.*)$", line)
        if m:
            errors.append({"file": m.group(1), "line": int(m.group(2)), "message": m.group(3)})
        elif line.startswith("! "):
            context = " ".join(l.strip() for l in lines[i + 1 : i + 3] if l.strip())
            errors.append({"file": None, "line": None, "message": line[2:] + (f" ({context})" if context else "")})
        elif "Warning:" in line and ("LaTeX" in line or "Package" in line):
            warnings.append(line.strip())
    cap = get_config("compile")["max_errors"]
    # file-line-error and "! " forms often duplicate each other.
    seen, unique = set(), []
    for e in errors:
        key = e["message"][:60]
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return {"errors": unique[:cap], "warnings": warnings[:cap]}


def compile_project(workdir: Path, main_file: str, build_dir: Path, engine: str = "pdflatex") -> dict:
    tool = available_compiler()
    if tool is None:
        return {
            "ok": None,
            "compiler": None,
            "message": "No local TeX compiler (latexmk or tectonic) is installed. "
            "Push and let Overleaf compile, or install one: sudo apt install latexmk texlive-latex-extra",
        }
    build_dir.mkdir(parents=True, exist_ok=True)
    if tool == "latexmk":
        cmd = [
            "latexmk",
            ENGINE_FLAGS.get(engine, "-pdf"),
            "-interaction=nonstopmode",
            "-file-line-error",
            "-halt-on-error",
            f"-outdir={build_dir}",
            main_file,
        ]
    else:
        cmd = ["tectonic", "--keep-logs", "--outdir", str(build_dir), main_file]
    timeout = get_config("compile")["timeout_seconds"]
    try:
        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "compiler": tool, "message": f"Compile timed out after {timeout}s."}

    log_path = build_dir / (Path(main_file).stem + ".log")
    log = log_path.read_text(errors="replace") if log_path.exists() else proc.stdout + proc.stderr
    parsed = parse_log(log)
    pdf = build_dir / (Path(main_file).stem + ".pdf")
    ok = proc.returncode == 0 and pdf.exists()
    return {
        "ok": ok,
        "compiler": tool,
        "pdf": str(pdf) if pdf.exists() else None,
        "message": "Compiled cleanly." if ok else "Compile failed.",
        **parsed,
    }
