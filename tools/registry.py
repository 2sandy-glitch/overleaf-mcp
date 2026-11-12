"""Registers every tool module's TOOLS on the MCP server.

New tool area: add <area>_tools.py with a TOOLS list of (function, effect)
and list the module in TOOL_MODULES.
"""

from mcp.types import ToolAnnotations

from tools import file_tools, latex_tools, project_tools

TOOL_MODULES = [project_tools, file_tools, latex_tools]

# effect -> what the client is told about the tool
EFFECTS = {
    "read": ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False),
    "write": ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False),
    "destructive": ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False),
    "remote_read": ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True),
    "remote": ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True),
}


def register_tools(server) -> None:
    for module in TOOL_MODULES:
        for fn, effect in module.TOOLS:
            server.add_tool(fn, annotations=EFFECTS[effect])
