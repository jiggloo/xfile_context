# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Cross-File Context Links MCP Server."""

from .cache import WorkingMemoryCache
from .config import Config
from .service import CrossFileContextService, ReadResult
from .storage import GraphExport, InMemoryStore, RelationshipStore

__version__ = "0.0.27"

__all__ = [
    "RelationshipStore",
    "InMemoryStore",
    "GraphExport",
    "WorkingMemoryCache",
    "CrossFileContextService",
    "ReadResult",
    "Config",
]

# Conditional import for MCP server (requires Python 3.10+ and mcp package)
try:
    from .mcp_server import CrossFileContextMCPServer

    __all__.append("CrossFileContextMCPServer")
except ImportError:
    # MCP package not available (e.g., Python < 3.10 or mcp not installed)
    pass
