"""FastMCP tool registration.

One module per tool group keeps schemas/descriptions easy to review.
"""

from __future__ import annotations

from fastmcp import FastMCP

from app.mcp.tools_read import register_read_tools
from app.mcp.tools_sync import register_sync_tools
from app.mcp.tools_write import register_write_tools


def register_all_tools(mcp: FastMCP) -> None:
    register_write_tools(mcp)
    register_read_tools(mcp)
    register_sync_tools(mcp)
