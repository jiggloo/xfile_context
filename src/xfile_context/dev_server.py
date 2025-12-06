# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Development server module for testing with 'mcp dev' and 'fastmcp run'.

This module exposes the FastMCP server instance as a global variable for
compatibility with MCP development tools that expect a discoverable server
object at module import time.

Usage:
    # With mcp dev (MCP Inspector) - run from repository root
    mcp dev src/xfile_context/dev_server.py:mcp

    # With fastmcp run - run from repository root
    fastmcp run src/xfile_context/dev_server.py:mcp

    The MCP Inspector will be available at http://localhost:6274 after startup.

Note:
    This module is for development/testing purposes only.
    For production use, run the server via: python -m xfile_context
"""

from xfile_context.mcp_server import CrossFileContextMCPServer

# Create server instance and expose the FastMCP object globally
# This is required for 'mcp dev' and 'fastmcp run' which expect
# a global FastMCP instance to be available at module level
_server = CrossFileContextMCPServer()
mcp = _server.mcp
