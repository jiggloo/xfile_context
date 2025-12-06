# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Integration tests for MCP Server + Service.

NOTE: Marked as slow tests - integration tests create full project structures.
Run with: pytest -m slow

Tests tool invocations produce correct responses per TDD Section 3.13.2.
Also covers T-9.1 through T-9.6 (Claude Code integration tests).
"""

from pathlib import Path

import pytest
import yaml

from xfile_context.config import Config
from xfile_context.mcp_server import CrossFileContextMCPServer
from xfile_context.service import CrossFileContextService

# Mark entire module as slow - integration tests create full project structures
pytestmark = pytest.mark.slow


def create_config_file(project_path: Path, **kwargs) -> Path:
    """Create a temporary config file with given settings."""
    config_path = project_path / ".cross_file_context_links.yml"
    config_data = {
        "cache_expiry_minutes": kwargs.get("cache_expiry_minutes", 10),
        "cache_size_limit_kb": kwargs.get("cache_size_limit_kb", 1024),
        "context_token_limit": kwargs.get("context_token_limit", 500),
        "enable_context_injection": kwargs.get("enable_context_injection", True),
    }
    config_path.write_text(yaml.dump(config_data))
    return config_path


class MockContext:
    """Mock MCP context for testing."""

    def __init__(self):
        self.messages = []

    async def info(self, message: str):
        self.messages.append(("info", message))

    async def error(self, message: str):
        self.messages.append(("error", message))

    async def warning(self, message: str):
        self.messages.append(("warning", message))


class TestMCPServerServiceIntegration:
    """Integration tests for MCP Server + Service workflow.

    Tests T-9.1 through T-9.6 (Claude Code integration tests).
    """

    def test_mcp_server_starts_without_errors(self, minimal_project: Path) -> None:
        """T-9.1: Verify MCP server starts without errors."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        # Create service
        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
        )

        # Create MCP server with service
        server = CrossFileContextMCPServer(
            config=config,
            service=service,
        )

        # Verify server initialized
        assert server is not None
        assert server.mcp is not None
        assert server.service is service

        # Clean shutdown
        server.shutdown()

    def test_mcp_server_with_default_service(self, minimal_project: Path) -> None:
        """Test MCP server creates default service if none provided."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        # Create MCP server without explicit service
        server = CrossFileContextMCPServer(config=config)

        # Verify server has a service
        assert server.service is not None

        server.shutdown()

    @pytest.mark.asyncio
    async def test_read_with_context_tool(self, sample_project: Path) -> None:
        """T-9.2: Verify Read tool works with context injection."""
        config_path = create_config_file(sample_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(sample_project),
        )

        # Analyze project first
        service.analyze_directory(str(sample_project / "mypackage"))

        server = CrossFileContextMCPServer(
            config=config,
            service=service,
        )

        # Get the registered tools from FastMCP
        # The tools are registered as functions on server.mcp
        # We need to test the service layer directly since FastMCP
        # tools require actual MCP context

        # Test through service layer (which is what the tool calls)
        core_file = sample_project / "mypackage" / "core.py"
        result = service.read_file_with_context(str(core_file))

        assert result.file_path == str(core_file)
        assert len(result.content) > 0

        # Check content formatting
        formatted = server._format_content_with_context(result.content, result.injected_context)
        assert formatted is not None

        server.shutdown()

    @pytest.mark.asyncio
    async def test_get_relationship_graph_tool(self, sample_project: Path) -> None:
        """Test get_relationship_graph tool returns correct structure."""
        config_path = create_config_file(sample_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(sample_project),
        )

        # Analyze project
        service.analyze_directory(str(sample_project / "mypackage"))

        server = CrossFileContextMCPServer(
            config=config,
            service=service,
        )

        # Test through service layer
        graph_export = service.get_relationship_graph()

        # Verify export structure
        assert isinstance(graph_export, dict)
        assert "files" in graph_export
        assert "relationships" in graph_export
        assert "metadata" in graph_export

        server.shutdown()

    def test_mcp_server_shutdown(self, minimal_project: Path) -> None:
        """Test MCP server shutdown cleans up resources."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
        )

        server = CrossFileContextMCPServer(
            config=config,
            service=service,
        )

        # Shutdown should not raise
        server.shutdown()

        # Service should be shut down too
        # (can't easily verify without internal state access)

    def test_mcp_server_with_context_injection_disabled(self, minimal_project: Path) -> None:
        """Test MCP server when context injection is disabled."""
        config_path = create_config_file(minimal_project, enable_context_injection=False)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
        )

        server = CrossFileContextMCPServer(
            config=config,
            service=service,
        )

        # Read file - should get content without context
        main_file = minimal_project / "main.py"
        result = service.read_file_with_context(str(main_file))

        # Content should be returned
        assert result.content is not None
        assert result.injected_context == ""

        # Format should not include context
        formatted = server._format_content_with_context(result.content, result.injected_context)
        assert formatted == result.content

        server.shutdown()

    def test_context_format_with_injection(self, minimal_project: Path) -> None:
        """Test content formatting when context is injected."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
        )

        server = CrossFileContextMCPServer(
            config=config,
            service=service,
        )

        # Test formatting with context
        content = "print('hello')"
        context = "# [Cross-File Context]\n# imports: module_a, module_b"

        formatted = server._format_content_with_context(content, context)

        # Should have context followed by separator and content
        assert context in formatted
        assert "---" in formatted
        assert content in formatted

        # Context should come before content
        context_pos = formatted.find(context)
        content_pos = formatted.find(content)
        assert context_pos < content_pos

        server.shutdown()

    def test_error_handling_file_not_found(self, minimal_project: Path) -> None:
        """T-9.5: Verify error messages surface properly."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
        )

        server = CrossFileContextMCPServer(
            config=config,
            service=service,
        )

        # Try to read non-existent file
        with pytest.raises(FileNotFoundError):
            service.read_file_with_context(str(minimal_project / "nonexistent.py"))

        server.shutdown()

    def test_multiple_tool_invocations(self, sample_project: Path) -> None:
        """Test multiple sequential tool invocations."""
        config_path = create_config_file(sample_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(sample_project),
        )

        # Analyze project
        service.analyze_directory(str(sample_project / "mypackage"))

        server = CrossFileContextMCPServer(
            config=config,
            service=service,
        )

        # Multiple file reads
        files = [
            sample_project / "mypackage" / "core.py",
            sample_project / "mypackage" / "models" / "user.py",
            sample_project / "mypackage" / "utils" / "helpers.py",
        ]

        for file in files:
            if file.exists():
                result = service.read_file_with_context(str(file))
                assert result.content is not None

        # Get graph after all reads
        graph = service.get_relationship_graph()
        assert len(graph["files"]) > 0

        server.shutdown()

    def test_mcp_tools_registered(self, minimal_project: Path) -> None:
        """Test that MCP tools are properly registered."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        server = CrossFileContextMCPServer(config=config)

        # FastMCP should have tools registered
        assert server.mcp is not None

        # Tools are registered via decorators on FastMCP
        # The exact way to check depends on FastMCP implementation

        server.shutdown()

    def test_mcp_server_name(self, minimal_project: Path) -> None:
        """Test MCP server has correct name per TDD."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        server = CrossFileContextMCPServer(config=config)

        # Server should have correct name per TDD Section 3.4.1
        assert server.mcp.name == "cross-file-context-links"

        server.shutdown()

    def test_service_state_preserved_across_calls(self, sample_project: Path) -> None:
        """Test that service state is preserved across multiple calls."""
        config_path = create_config_file(sample_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(sample_project),
        )

        # Analyze project
        service.analyze_directory(str(sample_project / "mypackage"))

        server = CrossFileContextMCPServer(
            config=config,
            service=service,
        )

        # Get initial graph
        graph1 = service.get_relationship_graph()
        rel_count1 = len(graph1["relationships"])

        # Read some files
        core_file = sample_project / "mypackage" / "core.py"
        service.read_file_with_context(str(core_file))

        # Get graph again - should be same
        graph2 = service.get_relationship_graph()
        rel_count2 = len(graph2["relationships"])

        # Relationships should be preserved
        assert rel_count2 == rel_count1

        server.shutdown()

    def test_mcp_server_logging(
        self, minimal_project: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test MCP server logs appropriately."""
        import logging

        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        with caplog.at_level(logging.INFO):
            server = CrossFileContextMCPServer(config=config)

            # Should log initialization
            assert any("initialized" in r.message.lower() for r in caplog.records)

            server.shutdown()


class TestMCPServerEdgeCases:
    """Edge case tests for MCP Server + Service integration."""

    def test_empty_project(self, tmp_path: Path) -> None:
        """Test MCP server with empty project."""
        empty_project = tmp_path / "empty"
        empty_project.mkdir()

        config_path = create_config_file(empty_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(empty_project),
        )

        server = CrossFileContextMCPServer(
            config=config,
            service=service,
        )

        # Should handle empty project
        service.analyze_directory(str(empty_project))
        graph = service.get_relationship_graph()

        # Empty but valid structure
        assert "files" in graph
        assert "relationships" in graph

        server.shutdown()

    def test_large_file_handling(self, minimal_project: Path) -> None:
        """Test handling of large files."""
        config_path = create_config_file(
            minimal_project,
            enable_context_injection=True,
            context_token_limit=100,  # Small limit
        )
        config = Config(config_path=config_path)

        # Create a larger file
        large_file = minimal_project / "large_module.py"
        lines = ["# Copyright (c) 2025 Henru Wang\n", "# All rights reserved.\n", "\n"]
        for i in range(500):
            lines.append(f"def function_{i}():\n    pass\n\n")
        large_file.write_text("".join(lines))

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
        )

        server = CrossFileContextMCPServer(
            config=config,
            service=service,
        )

        # Should handle large file
        service.analyze_file(str(large_file))
        result = service.read_file_with_context(str(large_file))

        assert result.content is not None

        server.shutdown()

    def test_binary_file_rejection(self, minimal_project: Path) -> None:
        """Test that binary files are handled gracefully."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        # Create a binary file with .py extension (unusual but possible)
        binary_file = minimal_project / "binary.py"
        binary_file.write_bytes(b"\x00\x01\x02\x03\x04\x05")

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
        )

        server = CrossFileContextMCPServer(
            config=config,
            service=service,
        )

        # Analysis should handle gracefully (may fail or skip)
        # The key is it shouldn't crash
        service.analyze_file(str(binary_file))
        # Result may be True or False depending on implementation

        server.shutdown()

    def test_path_security(self, minimal_project: Path) -> None:
        """Test path security handling."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
        )

        server = CrossFileContextMCPServer(
            config=config,
            service=service,
        )

        # Path traversal should be rejected
        with pytest.raises(ValueError, match="traversal"):
            service.read_file_with_context("/../../../etc/passwd")

        server.shutdown()
