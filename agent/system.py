"""Builds the MCP server: tools from tools/registry.py, prompts from prompts/."""

from mcp.server.mcpserver import MCPServer

from prompts.loader import register_prompts
from src import VERSION
from tools.registry import register_tools

INSTRUCTIONS = """\
Edits LaTeX projects that live on Overleaf (or any git/local LaTeX folder).
Edits land in a local working copy first; nothing reaches Overleaf until `push`.
Always `pull` before editing. Prefer `replace_section` / `edit_file` over rewriting
whole files. Show the user the `diff` and get a yes before `push`.
`project` is optional everywhere; it defaults to the configured default project.
"""


def build_server() -> MCPServer:
    server = MCPServer(name="overleaf", version=VERSION, instructions=INSTRUCTIONS)
    register_tools(server)
    register_prompts(server)
    return server
