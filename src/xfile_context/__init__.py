# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Cross-File Context Links MCP Server."""

from .cache import WorkingMemoryCache
from .config import Config
from .metrics_collector import (
    MetricsCollector,
    SessionMetrics,
    calculate_percentile_statistics,
    read_session_metrics,
)
from .query_api import QueryAPI
from .service import CrossFileContextService, ReadResult
from .storage import GraphExport, InMemoryStore, RelationshipStore
from .warning_formatter import StructuredWarning, WarningEmitter, WarningFormatter
from .warning_logger import WarningLogger, WarningStatistics, read_warnings_from_log
from .warning_suppression import WarningSuppressionManager

__version__ = "0.0.64"

__all__ = [
    "RelationshipStore",
    "InMemoryStore",
    "GraphExport",
    "WorkingMemoryCache",
    "CrossFileContextService",
    "ReadResult",
    "Config",
    "MetricsCollector",
    "SessionMetrics",
    "calculate_percentile_statistics",
    "read_session_metrics",
    "QueryAPI",
    "StructuredWarning",
    "WarningEmitter",
    "WarningFormatter",
    "WarningLogger",
    "WarningStatistics",
    "read_warnings_from_log",
    "WarningSuppressionManager",
]

# Conditional import for MCP server (requires Python 3.10+ and mcp package)
try:
    from .mcp_server import CrossFileContextMCPServer

    __all__.append("CrossFileContextMCPServer")
except ImportError:
    # MCP package not available (e.g., Python < 3.10 or mcp not installed)
    pass
