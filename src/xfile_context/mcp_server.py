# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""MCP Server Protocol Layer for Cross-File Context Links.

This module implements the MCP protocol layer (TDD Section 3.4.1) with ZERO business logic.
All business logic is delegated to CrossFileContextService per DD-6 (layered architecture).
"""

import argparse
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from xfile_context.cache import WorkingMemoryCache
from xfile_context.config import Config
from xfile_context.log_config import ensure_log_directories, get_default_data_root
from xfile_context.service import CrossFileContextService
from xfile_context.storage import InMemoryStore

logger = logging.getLogger(__name__)


class CrossFileContextMCPServer:
    """MCP Protocol Layer for Cross-File Context Links.

    Responsibilities (per TDD Section 3.4.1):
    - Initialize MCP server and register tools
    - Receive tool invocation requests from Claude Code
    - Translate MCP requests to service calls
    - Format service responses as MCP tool results
    - Handle MCP server lifecycle (startup, shutdown, health checks)

    Design Constraint (DD-6): This layer contains ZERO business logic.
    All analysis, caching, and context injection logic resides in CrossFileContextService.
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        service: Optional[CrossFileContextService] = None,
        data_root: Optional[Path] = None,
        session_id: Optional[str] = None,
    ):
        """Initialize MCP server.

        Args:
            config: Configuration object. If None, loads from default location.
            service: Service layer instance. If None, creates default service.
            data_root: Root directory for log files. If None, uses ~/.cross_file_context/
            session_id: Session ID for log filenames. If None, generates a UUID.
        """
        # Initialize configuration
        if config is None:
            config = Config()
        self.config = config

        # Initialize data root and session ID (Issue #150)
        self.data_root = data_root or get_default_data_root()
        self.session_id = session_id or str(uuid.uuid4())

        # Ensure log directories exist
        ensure_log_directories(self.data_root)

        # Initialize service layer
        if service is None:
            store = InMemoryStore()
            # Note: Cache requires file_event_timestamps dict from FileWatcher
            # For now, use empty dict as stub (full implementation in Task 4.3)
            file_event_timestamps: Dict[str, float] = {}
            cache = WorkingMemoryCache(
                file_event_timestamps=file_event_timestamps,
                size_limit_kb=config.cache_size_limit_kb,
            )
            service = CrossFileContextService(
                config=config,
                store=store,
                cache=cache,
                session_id=self.session_id,
                data_root=self.data_root,
            )
        self.service = service

        # Initialize FastMCP server
        # Server name per TDD Section 3.4.1
        self.mcp = FastMCP(name="cross-file-context-links")

        # Register tools
        self._register_tools()

        logger.info("CrossFileContextMCPServer initialized")

    def _register_tools(self) -> None:
        """Register MCP tools with the server.

        Registers:
        - read_with_context: Read file with cross-file context injection
        - get_relationship_graph: Export relationship graph
        """

        @self.mcp.tool()
        async def read_with_context(
            file_path: str,
            ctx: Context[ServerSession, None],
        ) -> Dict[str, Any]:
            """Read a Python file with automatic cross-file context injection.

            This tool reads a file and injects relevant context from related files
            (imports, function calls, class inheritance) to help understand the code.

            Args:
                file_path: Absolute or relative path to the Python file to read
                ctx: MCP context for logging and progress

            Returns:
                Dictionary with:
                - file_path: The path that was read
                - content: File content with injected context
                - warnings: List of any warnings (empty list if none)

            Raises:
                FileNotFoundError: If the file doesn't exist
                PermissionError: If the file can't be read
                ValueError: If the path is not a file
            """
            await ctx.info(f"Reading file with context: {file_path}")

            try:
                # Delegate to service layer (ZERO business logic here)
                result = self.service.read_file_with_context(file_path)

                # Format response per MCP specification
                response = {
                    "file_path": result.file_path,
                    "content": self._format_content_with_context(
                        result.content, result.injected_context
                    ),
                    "warnings": result.warnings,
                }

                await ctx.info(f"Successfully read {file_path}")
                return response

            except FileNotFoundError:
                await ctx.error(f"File not found: {file_path}")
                raise
            except PermissionError:
                await ctx.error(f"Permission denied: {file_path}")
                raise
            except Exception as e:
                await ctx.error(f"Unexpected error reading {file_path}: {e}")
                raise

        @self.mcp.tool()
        async def get_relationship_graph(
            ctx: Context[ServerSession, None],
        ) -> Dict[str, Any]:
            """Export the complete relationship graph for the codebase.

            Returns the full graph of file relationships including imports,
            function calls, and class inheritance.

            Args:
                ctx: MCP context for logging and progress

            Returns:
                Dictionary with:
                - nodes: List of file nodes
                - relationships: List of relationships between files
                - metadata: Graph metadata (timestamp, counts)
            """
            await ctx.info("Exporting relationship graph")

            try:
                # Delegate to service layer (ZERO business logic here)
                graph_export = self.service.get_relationship_graph()

                # Format response per MCP specification
                # graph_export may have to_dict method or be a dict directly
                if hasattr(graph_export, "to_dict"):
                    response: Dict[str, Any] = graph_export.to_dict()
                else:
                    # Already a dict (from InMemoryStore.export_graph)
                    response = graph_export

                await ctx.info(
                    f"Graph exported: {len(response.get('nodes', []))} nodes, "
                    f"{len(response.get('relationships', []))} relationships"
                )
                return response

            except Exception as e:
                await ctx.error(f"Error exporting relationship graph: {e}")
                raise

        logger.info("MCP tools registered: read_with_context, get_relationship_graph")

    def _format_content_with_context(self, content: str, injected_context: str) -> str:
        """Format file content with injected context.

        If context injection is enabled and context is available, prepends it to the content.
        Format per TDD Section 3.8.3:
        - Header: [Cross-File Context]
        - Dependency summary
        - Snippets with location + signature
        - Separator: ---
        - File content

        Args:
            content: Original file content
            injected_context: Context to inject (empty string if none)

        Returns:
            Formatted content with context prepended
        """
        if not self.config.enable_context_injection:
            return content

        if not injected_context:
            return content

        # Format per TDD Section 3.8.3
        return f"{injected_context}\n---\n{content}"

    def run(self, transport: str = "stdio") -> None:
        """Run the MCP server.

        Args:
            transport: Transport type to use. Options:
                - "stdio": Standard input/output (default for Claude Code)
                - "streamable-http": HTTP transport
                - "sse": Server-sent events transport
        """
        logger.info(f"Starting MCP server with {transport} transport")
        self.mcp.run(transport=transport)  # type: ignore[arg-type]

    def shutdown(self) -> None:
        """Shutdown the MCP server and cleanup resources."""
        logger.info("Shutting down MCP server")
        self.service.shutdown()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Cross-File Context Links MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help=(
            "Root directory for log files (injections, warnings, session_metrics). "
            f"Default: {get_default_data_root()}"
        ),
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "streamable-http", "sse"],
        default="stdio",
        help="Transport type for MCP server. Default: stdio",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point for MCP server.

    Initializes logging and starts the server with stdio transport (Claude Code default).

    Note: setup_logging() from logging_setup.py is NOT currently called here.
    The MCP server uses basic logging configuration. See Issue #150 for details.
    """
    # Parse command-line arguments
    args = parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create and run server with data_root from CLI
    server = CrossFileContextMCPServer(data_root=args.data_root)
    logger.info(
        f"Starting MCP server with data_root={server.data_root}, session_id={server.session_id}"
    )
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
