# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""CrossFileContextService - Business logic layer for MCP server.

This is a stub/interface for Task 4.3. The MCP server (Task 4.2) depends on this interface
but the full implementation will be completed in Task 4.3.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from .cache import WorkingMemoryCache
from .config import Config
from .storage import GraphExport, RelationshipStore

logger = logging.getLogger(__name__)

# Security constants
_MAX_FILEPATH_LENGTH = 4096  # Maximum filepath length to prevent DoS
_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB max file size


class ReadResult:
    """Result of reading a file with context injection."""

    def __init__(
        self,
        file_path: str,
        content: str,
        injected_context: str,
        warnings: List[str],
    ):
        """Initialize read result.

        Args:
            file_path: Path to the file that was read
            content: File content
            injected_context: Context that was injected
            warnings: Any warnings generated during read
        """
        self.file_path = file_path
        self.content = content
        self.injected_context = injected_context
        self.warnings = warnings

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MCP response."""
        return {
            "file_path": self.file_path,
            "content": self.content,
            "injected_context": self.injected_context,
            "warnings": self.warnings,
        }


class CrossFileContextService:
    """Business logic coordinator for cross-file context analysis.

    This service owns all analytical components and orchestrates the context injection workflow.
    Currently a stub implementation for Task 4.2. Full implementation in Task 4.3.

    Responsibilities (per TDD Section 3.4.2):
    - Initialize and coordinate all subsystems (analyzer, watcher, cache, store,
      warning system, metrics)
    - Handle file read requests with context injection
    - Provide relationship graph queries and export
    - Manage component lifecycle and configuration
    """

    def __init__(
        self,
        config: Config,
        store: RelationshipStore,
        cache: WorkingMemoryCache,
    ):
        """Initialize the service with its dependencies.

        Args:
            config: Configuration object
            store: Relationship store for graph data
            cache: Working memory cache for performance
        """
        self.config = config
        self.store = store
        self.cache = cache
        logger.info("CrossFileContextService initialized (stub)")

    def _validate_filepath(self, filepath: str) -> None:
        """Validate filepath for security concerns.

        Prevents path traversal attacks and other security issues
        by validating the filepath before any file operations.

        Args:
            filepath: Path to validate.

        Raises:
            ValueError: If filepath contains path traversal patterns,
                control characters, or exceeds length limits.
        """
        # Check for control characters first (null bytes, etc.)
        if any(ord(c) < 32 and c not in ("\t", "\n", "\r") for c in filepath):
            raise ValueError("Invalid characters in filepath")

        # Check maximum length to prevent DoS
        if len(filepath) > _MAX_FILEPATH_LENGTH:
            raise ValueError(f"Filepath too long: {len(filepath)} > {_MAX_FILEPATH_LENGTH}")

        # Check for path traversal patterns
        if "/.." in filepath or filepath.startswith("..") or "\\.." in filepath:
            raise ValueError("Path traversal not allowed")

    def read_file_with_context(self, file_path: str) -> ReadResult:
        """Read a file and inject relevant cross-file context.

        This is a stub implementation for Task 4.2.
        Full implementation in Task 4.3 will include context injection workflow.

        Args:
            file_path: Path to file to read

        Returns:
            ReadResult with file content and injected context

        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If file can't be read
            ValueError: If path validation fails (traversal, control chars, etc.)
        """
        # Security: Validate filepath before any operations
        self._validate_filepath(file_path)

        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # Security: Check file size before reading to prevent DoS
        try:
            file_size = path.stat().st_size
            if file_size > _MAX_FILE_SIZE_BYTES:
                raise ValueError(f"File too large: {file_size} bytes > {_MAX_FILE_SIZE_BYTES}")
        except OSError as e:
            raise PermissionError(f"Cannot access file: {file_path}") from e

        # Read file content
        try:
            content = path.read_text(encoding="utf-8")
        except PermissionError as e:
            raise PermissionError(f"Permission denied reading file: {file_path}") from e

        # Stub: No context injection yet (Task 4.3)
        injected_context = ""
        warnings: List[str] = []

        logger.debug(f"Read file {file_path} ({len(content)} bytes)")

        return ReadResult(
            file_path=file_path,
            content=content,
            injected_context=injected_context,
            warnings=warnings,
        )

    def get_relationship_graph(self) -> GraphExport:
        """Get the full relationship graph for export.

        This is a stub implementation for Task 4.2.
        Full implementation in Task 4.3 will query the relationship store.

        Returns:
            GraphExport object with current graph state
        """
        # Stub: Return empty graph for now
        return self.store.export_graph()

    def get_dependents(self, file_path: str) -> List[Dict[str, Any]]:
        """Get files that depend on the given file.

        This is a stub implementation for Task 4.2.
        Full implementation in Task 4.3.

        Args:
            file_path: Path to file to query

        Returns:
            List of relationship dictionaries
        """
        # Stub: Return empty list for now
        return []

    def shutdown(self) -> None:
        """Shutdown the service and cleanup resources.

        This is a stub implementation for Task 4.2.
        Full implementation in Task 4.3 will handle cleanup.
        """
        logger.info("CrossFileContextService shutdown")
