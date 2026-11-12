"""Loads the prompts/*.md playbooks and exposes them as MCP prompts.

The server stays generic; use cases (resume tailoring, paper revision, cover
letters...) are just recipe files. Drop a ``<name>.md`` into
~/.config/overleaf-mcp/recipes/ to add your own — no code change needed.

File format:
    ---
    name: tailor_resume
    description: one line
    arguments: job_description, project, notes
    ---
    Body with {job_description} style placeholders.
"""

import inspect
from dataclasses import dataclass
from pathlib import Path

from mcp.server.mcpserver.prompts.base import Prompt

from src import prompt_dirs


@dataclass
class Recipe:
    name: str
    description: str
    arguments: list[str]
    body: str
    source: Path

    def render(self, values: dict[str, str]) -> str:
        out = self.body
        for arg in self.arguments:
            out = out.replace("{" + arg + "}", values.get(arg) or "")
        return out


def parse_recipe(path: Path) -> Recipe:
    text = path.read_text()
    meta: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        _, header, body = text.split("---", 2)
        for line in header.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    args = [a.strip() for a in meta.get("arguments", "").split(",") if a.strip()]
    return Recipe(
        name=meta.get("name", path.stem),
        description=meta.get("description", ""),
        arguments=args,
        body=body.strip() + "\n",
        source=path,
    )


def load_recipes(dirs: list[Path]) -> dict[str, Recipe]:
    recipes: dict[str, Recipe] = {}
    for d in dirs:
        if d.is_dir():
            for f in sorted(d.glob("*.md")):
                r = parse_recipe(f)
                recipes[r.name] = r
    return recipes


def recipe_function(recipe: Recipe):
    """Build a function whose signature matches the recipe's arguments,
    so the MCP SDK can advertise them as prompt arguments."""

    def render(**kwargs: str) -> str:
        return recipe.render(kwargs)

    first_required = recipe.arguments[:1]
    params = [
        inspect.Parameter(
            a,
            inspect.Parameter.KEYWORD_ONLY,
            annotation=str,
            default=inspect.Parameter.empty if a in first_required else "",
        )
        for a in recipe.arguments
    ]
    render.__signature__ = inspect.Signature(params, return_annotation=str)
    render.__annotations__ = {a: str for a in recipe.arguments} | {"return": str}
    render.__name__ = recipe.name
    render.__doc__ = recipe.description
    return render


def register_prompts(server) -> None:
    for recipe in load_recipes(prompt_dirs()).values():
        server.add_prompt(Prompt.from_function(recipe_function(recipe), name=recipe.name, description=recipe.description))
