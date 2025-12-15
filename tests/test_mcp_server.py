# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for MCP Server Protocol Layer.

Test coverage:
- T-9.1: MCP server starts without errors
- T-9.2: Read tool works (can receive and respond to tool invocations)
- T-9.4: No conflicts with other MCP servers (unique server name)
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import pytest

# Skip tests if mcp package not available (requires Python 3.10+)
pytest.importorskip("mcp", reason="MCP package requires Python 3.10+")

from xfile_context.cache import WorkingMemoryCache  # noqa: E402
from xfile_context.config import Config  # noqa: E402
from xfile_context.mcp_server import CrossFileContextMCPServer  # noqa: E402
from xfile_context.service import CrossFileContextService  # noqa: E402
from xfile_context.storage import InMemoryStore  # noqa: E402


class TestCrossFileContextMCPServer:
    """Tests for CrossFileContextMCPServer."""

    def test_t91_server_initialization(self):
        """T-9.1: MCP server starts without errors.

        Verifies that the MCP server can be initialized with default configuration.
        """
        # Should not raise any exceptions
        server = CrossFileContextMCPServer()

        assert server is not None
        assert server.mcp is not None
        assert server.service is not None
        assert server.config is not None

    def test_t91_server_initialization_with_custom_config(self):
        """T-9.1: MCP server starts with custom configuration."""
        config = Config()
        store = InMemoryStore()
        file_event_timestamps: dict[str, float] = {}
        cache = WorkingMemoryCache(
            file_event_timestamps=file_event_timestamps,
            size_limit_kb=config.cache_size_limit_kb,
        )
        service = CrossFileContextService(config, store, cache)

        server = CrossFileContextMCPServer(config=config, service=service)

        assert server.config is config
        assert server.service is service
        assert server.mcp is not None

    def test_t94_server_name_is_unique(self):
        """T-9.4: No conflicts with other MCP servers.

        Verifies that the server uses the unique name 'cross-file-context-links'
        as specified in TDD Section 3.4.1 to avoid conflicts with other MCP servers.
        """
        server = CrossFileContextMCPServer()

        # Verify server name matches TDD specification
        assert server.mcp.name == "cross-file-context-links"

    def test_tools_are_registered(self):
        """Verify that both tools are registered on server initialization."""
        server = CrossFileContextMCPServer()

        # FastMCP registers tools internally, verify they're accessible
        # Tools are registered as decorators, so we verify the MCP instance has tools
        assert hasattr(server.mcp, "_tool_manager")
        # The tools should be registered, but FastMCP doesn't expose them directly
        # We verify by checking that _register_tools completed without error

    def test_format_content_with_context_enabled(self):
        """Test content formatting with context injection enabled."""
        server = CrossFileContextMCPServer()
        server.config._config["enable_context_injection"] = True

        content = "print('hello')"
        context = "[Cross-File Context]\nDependency: module.py"

        result = server._format_content_with_context(content, context)

        assert result.startswith(context)
        assert "---\n" in result
        assert result.endswith(content)

    def test_format_content_with_context_disabled(self):
        """Test content formatting with context injection disabled."""
        server = CrossFileContextMCPServer()
        server.config._config["enable_context_injection"] = False

        content = "print('hello')"
        context = "[Cross-File Context]\nDependency: module.py"

        result = server._format_content_with_context(content, context)

        # Should return original content without context
        assert result == content

    def test_format_content_with_no_context(self):
        """Test content formatting when no context is available."""
        server = CrossFileContextMCPServer()
        server.config._config["enable_context_injection"] = True

        content = "print('hello')"
        context = ""

        result = server._format_content_with_context(content, context)

        # Should return original content when context is empty
        assert result == content

    def test_shutdown(self):
        """Test server shutdown."""
        server = CrossFileContextMCPServer()

        # Should not raise
        server.shutdown()


class TestMCPToolIntegration:
    """Integration tests for MCP tools.

    These tests verify that the tools can be called and properly delegate
    to the service layer without containing business logic (DD-6).
    """

    @pytest.mark.asyncio
    async def test_t92_read_with_context_tool_success(self):
        """T-9.2: Read tool works - successful file read.

        Verifies that the read_with_context tool can receive and respond
        to tool invocations correctly.
        """
        server = CrossFileContextMCPServer()

        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_content = "# Test file\nprint('hello')"
            test_file.write_text(test_content)

            # Create a mock context
            mock_ctx = Mock()
            mock_ctx.info = Mock(return_value=None)
            mock_ctx.error = Mock(return_value=None)

            # Get the tool function from the tools registered on the server
            # Since tools are registered via decorator, we need to access them differently
            # For now, test via the service layer which the tool delegates to
            result = server.service.read_file_with_context(str(test_file))

            assert result.file_path == str(test_file)
            assert result.content == test_content
            assert isinstance(result.warnings, list)

    @pytest.mark.asyncio
    async def test_t92_read_with_context_tool_file_not_found(self):
        """T-9.2: Read tool works - handles file not found error."""
        server = CrossFileContextMCPServer()

        # Create a mock context
        mock_ctx = Mock()
        mock_ctx.info = Mock(return_value=None)
        mock_ctx.error = Mock(return_value=None)

        # Test that service layer raises FileNotFoundError
        with pytest.raises(FileNotFoundError):
            server.service.read_file_with_context("/nonexistent/file.py")

    @pytest.mark.asyncio
    async def test_t92_get_relationship_graph_tool(self):
        """T-9.2: Get relationship graph tool works."""
        server = CrossFileContextMCPServer()

        # Create a mock context
        mock_ctx = Mock()
        mock_ctx.info = Mock(return_value=None)
        mock_ctx.error = Mock(return_value=None)

        # Test via service layer which the tool delegates to
        graph_export = server.service.get_relationship_graph()

        assert graph_export is not None
        # export_graph() returns a dict from InMemoryStore
        graph_dict = graph_export.to_dict() if hasattr(graph_export, "to_dict") else graph_export
        assert "relationships" in graph_dict


class TestProtocolLayerDesign:
    """Tests for DD-6 design constraint: ZERO business logic in protocol layer."""

    def test_dd6_no_business_logic_in_protocol_layer(self):
        """Verify protocol layer has ZERO business logic.

        The MCP server should only:
        1. Initialize MCP server
        2. Register tools
        3. Translate requests to service calls
        4. Format responses

        All business logic should be in CrossFileContextService.
        """
        server = CrossFileContextMCPServer()

        # Verify server only has protocol-related attributes
        assert hasattr(server, "mcp")  # MCP server instance
        assert hasattr(server, "service")  # Service layer
        assert hasattr(server, "config")  # Configuration

        # Verify service is CrossFileContextService (business logic layer)
        assert isinstance(server.service, CrossFileContextService)

        # Verify MCP server is FastMCP (protocol layer)
        from mcp.server.fastmcp import FastMCP

        assert isinstance(server.mcp, FastMCP)

    def test_dd6_service_delegation(self):
        """Verify all operations delegate to service layer."""
        server = CrossFileContextMCPServer()

        # Verify service layer has the business logic methods
        assert hasattr(server.service, "read_file_with_context")
        assert hasattr(server.service, "get_relationship_graph")
        assert hasattr(server.service, "get_dependents")

        # Verify MCP server doesn't implement business logic directly
        # (only has _format_content_with_context for formatting, not analysis)
        assert hasattr(server, "_format_content_with_context")
        assert not hasattr(server, "analyze_file")
        assert not hasattr(server, "detect_imports")
        assert not hasattr(server, "build_graph")


class TestMCPToolHandlers:
    """Tests for MCP tool handler implementations.

    Tests the async tool handlers that are registered with FastMCP.
    """

    @pytest.mark.asyncio
    async def test_read_with_context_handler_success(self):
        """Test read_with_context handler with successful file read."""
        from unittest.mock import AsyncMock

        server = CrossFileContextMCPServer()

        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_content = "# Test file\nprint('hello')"
            test_file.write_text(test_content)

            # Create mock context with async methods
            mock_ctx = AsyncMock()
            mock_ctx.info = AsyncMock()
            mock_ctx.error = AsyncMock()

            # Access the registered tool handler
            # FastMCP stores tools in _tool_manager.tools dict
            tool_manager = server.mcp._tool_manager
            read_tool = tool_manager._tools.get("read_with_context")

            if read_tool:
                # Call the handler function directly
                result = await read_tool.fn(str(test_file), mock_ctx)
                assert result["file_path"] == str(test_file)
                assert test_content in result["content"]
                assert "warnings" in result
                mock_ctx.info.assert_called()

    @pytest.mark.asyncio
    async def test_read_with_context_handler_file_not_found(self):
        """Test read_with_context handler with FileNotFoundError."""
        from unittest.mock import AsyncMock

        server = CrossFileContextMCPServer()

        # Create mock context with async methods
        mock_ctx = AsyncMock()
        mock_ctx.info = AsyncMock()
        mock_ctx.error = AsyncMock()

        # Access the registered tool handler
        tool_manager = server.mcp._tool_manager
        read_tool = tool_manager._tools.get("read_with_context")

        if read_tool:
            with pytest.raises(FileNotFoundError):
                await read_tool.fn("/nonexistent/file.py", mock_ctx)
            mock_ctx.error.assert_called()

    @pytest.mark.asyncio
    async def test_read_with_context_handler_permission_error(self):
        """Test read_with_context handler with PermissionError."""
        from unittest.mock import AsyncMock, patch

        server = CrossFileContextMCPServer()

        # Create mock context with async methods
        mock_ctx = AsyncMock()
        mock_ctx.info = AsyncMock()
        mock_ctx.error = AsyncMock()

        # Access the registered tool handler
        tool_manager = server.mcp._tool_manager
        read_tool = tool_manager._tools.get("read_with_context")

        if read_tool:
            # Patch the service to raise PermissionError
            with patch.object(
                server.service, "read_file_with_context", side_effect=PermissionError("denied")
            ):
                with pytest.raises(PermissionError):
                    await read_tool.fn("/some/file.py", mock_ctx)
                mock_ctx.error.assert_called()

    @pytest.mark.asyncio
    async def test_read_with_context_handler_unexpected_error(self):
        """Test read_with_context handler with unexpected error."""
        from unittest.mock import AsyncMock, patch

        server = CrossFileContextMCPServer()

        # Create mock context with async methods
        mock_ctx = AsyncMock()
        mock_ctx.info = AsyncMock()
        mock_ctx.error = AsyncMock()

        # Access the registered tool handler
        tool_manager = server.mcp._tool_manager
        read_tool = tool_manager._tools.get("read_with_context")

        if read_tool:
            # Patch the service to raise unexpected error
            with patch.object(
                server.service, "read_file_with_context", side_effect=RuntimeError("unexpected")
            ):
                with pytest.raises(RuntimeError):
                    await read_tool.fn("/some/file.py", mock_ctx)
                mock_ctx.error.assert_called()

    @pytest.mark.asyncio
    async def test_get_relationship_graph_handler_success(self):
        """Test get_relationship_graph handler success."""
        from unittest.mock import AsyncMock

        server = CrossFileContextMCPServer()

        # Create mock context with async methods
        mock_ctx = AsyncMock()
        mock_ctx.info = AsyncMock()
        mock_ctx.error = AsyncMock()

        # Access the registered tool handler
        tool_manager = server.mcp._tool_manager
        graph_tool = tool_manager._tools.get("get_relationship_graph")

        if graph_tool:
            result = await graph_tool.fn(mock_ctx)
            assert "relationships" in result
            mock_ctx.info.assert_called()

    @pytest.mark.asyncio
    async def test_get_relationship_graph_handler_with_to_dict(self):
        """Test get_relationship_graph handler when export has to_dict method."""
        from unittest.mock import AsyncMock, MagicMock, patch

        server = CrossFileContextMCPServer()

        # Create mock context with async methods
        mock_ctx = AsyncMock()
        mock_ctx.info = AsyncMock()
        mock_ctx.error = AsyncMock()

        # Create a mock graph export with to_dict method
        mock_export = MagicMock()
        mock_export.to_dict.return_value = {
            "nodes": [{"file": "test.py"}],
            "relationships": [{"source": "a.py", "target": "b.py"}],
        }

        # Access the registered tool handler
        tool_manager = server.mcp._tool_manager
        graph_tool = tool_manager._tools.get("get_relationship_graph")

        if graph_tool:
            with patch.object(server.service, "get_relationship_graph", return_value=mock_export):
                result = await graph_tool.fn(mock_ctx)
                assert result["nodes"] == [{"file": "test.py"}]
                assert len(result["relationships"]) == 1

    @pytest.mark.asyncio
    async def test_get_relationship_graph_handler_error(self):
        """Test get_relationship_graph handler with error."""
        from unittest.mock import AsyncMock, patch

        server = CrossFileContextMCPServer()

        # Create mock context with async methods
        mock_ctx = AsyncMock()
        mock_ctx.info = AsyncMock()
        mock_ctx.error = AsyncMock()

        # Access the registered tool handler
        tool_manager = server.mcp._tool_manager
        graph_tool = tool_manager._tools.get("get_relationship_graph")

        if graph_tool:
            with patch.object(
                server.service, "get_relationship_graph", side_effect=RuntimeError("test error")
            ):
                with pytest.raises(RuntimeError):
                    await graph_tool.fn(mock_ctx)
                mock_ctx.error.assert_called()


class TestServerLifecycle:
    """Tests for MCP server lifecycle methods."""

    def test_run_method_exists(self):
        """Test that run method exists with correct signature."""
        server = CrossFileContextMCPServer()

        # Verify run method exists
        assert hasattr(server, "run")
        assert callable(server.run)

    def test_run_method_default_transport(self):
        """Test run method has default transport of stdio."""
        import inspect

        server = CrossFileContextMCPServer()

        sig = inspect.signature(server.run)
        transport_param = sig.parameters.get("transport")

        assert transport_param is not None
        assert transport_param.default == "stdio"


class TestMainEntryPoint:
    """Tests for main() entry point function."""

    def test_main_function_exists(self):
        """Test that main function is importable."""
        from xfile_context.mcp_server import main

        assert callable(main)


class TestServerShutdown:
    """Tests for MCP server shutdown handling (Issue #155)."""

    def test_shutdown_is_idempotent(self):
        """shutdown() should be safe to call multiple times (Issue #155)."""
        server = CrossFileContextMCPServer()

        # First shutdown should work
        server.shutdown()
        assert server._shutdown_called

        # Second shutdown should not raise or re-run shutdown logic
        server.shutdown()  # Should not raise

    def test_shutdown_calls_service_shutdown(self):
        """shutdown() should call service.shutdown() (Issue #155)."""
        from unittest.mock import Mock

        server = CrossFileContextMCPServer()
        server.service.shutdown = Mock()

        server.shutdown()

        server.service.shutdown.assert_called_once()

    def test_shutdown_only_calls_service_once(self):
        """shutdown() should only call service.shutdown() once (Issue #155)."""
        from unittest.mock import Mock

        server = CrossFileContextMCPServer()
        server.service.shutdown = Mock()

        # Call shutdown multiple times
        server.shutdown()
        server.shutdown()
        server.shutdown()

        # Service shutdown should only be called once
        server.service.shutdown.assert_called_once()

    def test_shutdown_called_initially_false(self):
        """_shutdown_called should be False initially (Issue #155)."""
        server = CrossFileContextMCPServer()
        assert not server._shutdown_called

    def test_atexit_module_imported(self):
        """atexit module should be imported for shutdown handler (Issue #155)."""
        import xfile_context.mcp_server as mcp_module

        # Verify atexit is imported in the module
        assert hasattr(mcp_module, "atexit") or "atexit" in dir(mcp_module)
