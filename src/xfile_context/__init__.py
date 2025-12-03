# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Cross-File Context Links MCP Server."""

from xfile_context.cache import WorkingMemoryCache
from xfile_context.config import Config
from xfile_context.metrics_collector import (
    MetricsCollector,
    SessionMetrics,
    calculate_percentile_statistics,
    read_session_metrics,
)
from xfile_context.query_api import QueryAPI
from xfile_context.service import CrossFileContextService, ReadResult
from xfile_context.storage import GraphExport, InMemoryStore, RelationshipStore
from xfile_context.warning_formatter import StructuredWarning, WarningEmitter, WarningFormatter
from xfile_context.warning_logger import WarningLogger, WarningStatistics, read_warnings_from_log
from xfile_context.warning_suppression import WarningSuppressionManager

__version__ = "0.0.71"

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
    from xfile_context.mcp_server import CrossFileContextMCPServer

    __all__.append("CrossFileContextMCPServer")
except ImportError:
    # MCP package not available (e.g., Python < 3.10 or mcp not installed)
    pass
