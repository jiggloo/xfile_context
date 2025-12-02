# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""CrossFileContextService - Business logic layer for MCP server.

This module implements the core business logic coordinator (TDD Section 3.4.2)
that owns all analytical components and orchestrates the context injection workflow.

Key Responsibilities:
- Initialize and coordinate all subsystems (analyzer, watcher, cache, store, graph)
- Handle file read requests with context injection (Section 3.8)
- Provide relationship graph queries and export
- Manage component lifecycle and configuration
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import tiktoken

from .analyzers.python_analyzer import PythonAnalyzer
from .cache import WorkingMemoryCache
from .config import Config
from .detectors import (
    ClassInheritanceDetector,
    ConditionalImportDetector,
    DetectorRegistry,
    FunctionCallDetector,
    ImportDetector,
    WildcardImportDetector,
)
from .file_watcher import FileWatcher
from .graph_updater import GraphUpdater
from .models import Relationship, RelationshipGraph, RelationshipType
from .storage import GraphExport, InMemoryStore, RelationshipStore

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

    This service owns all analytical components and orchestrates the context
    injection workflow per TDD Section 3.4.2.

    Owned Components (per Section 3.4.2):
    - PythonAnalyzer: Performs Python file analysis
    - FileWatcher: Monitors file system changes
    - WorkingMemoryCache: Caches recently-read content
    - RelationshipStore: Stores relationship graph
    - RelationshipGraph: In-memory graph representation
    - GraphUpdater: Handles incremental updates

    Context Injection Workflow (Section 3.8):
    1. Receive read request for target_file
    2. Check cache for recent read of target_file
    3. If cache miss: Read file from disk
    4. Query relationship store for dependencies of target_file
    5. For each dependency, check if cached (fresh within 10 min)
    6. Assemble context snippets (location + signature only)
    7. Return file content + injected context

    Design Constraint (DD-6):
    Service layer is storage-agnostic. Uses RelationshipStore interface,
    allowing v0.2.0 to swap InMemoryStore → SQLiteStore with minimal changes.
    """

    def __init__(
        self,
        config: Config,
        store: Optional[RelationshipStore] = None,
        cache: Optional[WorkingMemoryCache] = None,
        project_root: Optional[str] = None,
        file_watcher: Optional[FileWatcher] = None,
        graph: Optional[RelationshipGraph] = None,
        analyzer: Optional[PythonAnalyzer] = None,
        graph_updater: Optional[GraphUpdater] = None,
    ):
        """Initialize the service with its dependencies.

        Supports dependency injection for testing while providing sensible
        defaults for production use.

        Args:
            config: Configuration object
            store: Relationship store for graph data (default: InMemoryStore)
            cache: Working memory cache (default: creates new cache)
            project_root: Root directory for file watching (default: cwd)
            file_watcher: FileWatcher instance (default: creates new watcher)
            graph: RelationshipGraph instance (default: creates new graph)
            analyzer: PythonAnalyzer instance (default: creates new analyzer)
            graph_updater: GraphUpdater instance (default: creates new updater)
        """
        self.config = config
        self._project_root = Path(project_root) if project_root else Path.cwd()

        # Initialize store (storage-agnostic per DD-4)
        self.store = store if store is not None else InMemoryStore()

        # Initialize graph (used by analyzer and graph_updater)
        self._graph = graph if graph is not None else RelationshipGraph()

        # Initialize file watcher first (cache needs timestamps reference)
        self._file_watcher = (
            file_watcher
            if file_watcher is not None
            else FileWatcher(
                project_root=str(self._project_root),
                user_ignore_patterns=(
                    set(config.ignore_patterns) if config.ignore_patterns else None
                ),
            )
        )

        # Initialize cache with file watcher timestamps
        self.cache = (
            cache
            if cache is not None
            else WorkingMemoryCache(
                file_event_timestamps=self._file_watcher.file_event_timestamps,
                size_limit_kb=config.cache_size_limit_kb,
            )
        )

        # Initialize detector registry with default detectors (per TDD Section 3.4.4)
        self._detector_registry = DetectorRegistry()
        self._detector_registry.register(ImportDetector())
        self._detector_registry.register(ConditionalImportDetector())
        self._detector_registry.register(WildcardImportDetector())
        self._detector_registry.register(FunctionCallDetector())
        self._detector_registry.register(ClassInheritanceDetector())

        # Initialize analyzer
        self._analyzer = (
            analyzer
            if analyzer is not None
            else PythonAnalyzer(
                graph=self._graph,
                detector_registry=self._detector_registry,
            )
        )

        # Initialize graph updater
        self._graph_updater = (
            graph_updater
            if graph_updater is not None
            else GraphUpdater(
                graph=self._graph,
                analyzer=self._analyzer,
                file_watcher=self._file_watcher,
            )
        )

        # Track if watcher is running
        self._watcher_running = False

        # Initialize tiktoken encoder for token counting (TDD Section 3.8.4)
        # Use cl100k_base encoding (compatible with Claude/GPT-4)
        # Lazy initialization to avoid network calls in __init__
        self._token_encoder: Optional[tiktoken.Encoding] = None

        logger.info(f"CrossFileContextService initialized with project_root={self._project_root}")

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

    def start_file_watcher(self) -> None:
        """Start the file watcher for monitoring changes.

        Call this to enable automatic re-analysis when files change.
        """
        if not self._watcher_running:
            self._file_watcher.start()
            self._watcher_running = True
            logger.info("FileWatcher started")

    def stop_file_watcher(self) -> None:
        """Stop the file watcher."""
        if self._watcher_running:
            self._file_watcher.stop()
            self._watcher_running = False
            logger.info("FileWatcher stopped")

    def process_pending_changes(self) -> Dict[str, Any]:
        """Process any pending file changes detected by FileWatcher.

        Returns:
            Statistics about processed changes.
        """
        return self._graph_updater.process_pending_changes()

    def analyze_file(self, file_path: str) -> bool:
        """Analyze a single file and add its relationships to the graph.

        Args:
            file_path: Path to Python file to analyze.

        Returns:
            True if analysis succeeded, False otherwise.
        """
        self._validate_filepath(file_path)
        return self._analyzer.analyze_file(file_path)

    def analyze_directory(self, directory_path: Optional[str] = None) -> Dict[str, Any]:
        """Analyze all Python files in a directory.

        Args:
            directory_path: Path to directory (default: project_root).

        Returns:
            Statistics about analyzed files.
        """
        dir_path = Path(directory_path) if directory_path else self._project_root

        stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "elapsed_ms": 0.0,
        }

        start_time = time.time()

        for py_file in dir_path.rglob("*.py"):
            file_path = str(py_file)

            # Check if file should be ignored
            if self._file_watcher.should_ignore(file_path):
                stats["skipped"] += 1
                continue

            stats["total"] += 1

            try:
                if self._analyzer.analyze_file(file_path):
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
            except Exception as e:
                logger.error(f"Error analyzing {file_path}: {e}")
                stats["failed"] += 1

        stats["elapsed_ms"] = (time.time() - start_time) * 1000
        logger.info(
            f"Analyzed {stats['total']} files in {stats['elapsed_ms']:.1f}ms: "
            f"{stats['success']} success, {stats['failed']} failed, {stats['skipped']} skipped"
        )

        return stats

    def read_file_with_context(self, file_path: str) -> ReadResult:
        """Read a file and inject relevant cross-file context.

        Implements the context injection workflow from TDD Section 3.8:
        1. Validate and read file content
        2. Query relationship graph for dependencies
        3. Assemble context snippets in priority order
        4. Format injected context per Section 3.8.3

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

        warnings: List[str] = []
        injected_context = ""

        # Check if context injection is enabled
        if not self.config.enable_context_injection:
            logger.debug("Context injection disabled, returning file content only")
            return ReadResult(
                file_path=file_path,
                content=content,
                injected_context="",
                warnings=warnings,
            )

        # Get dependencies for this file from the graph
        dependencies = self._get_file_dependencies(file_path)

        if dependencies:
            # Assemble and format context
            injected_context, context_warnings = self._assemble_context(file_path, dependencies)
            warnings.extend(context_warnings)

        logger.debug(
            f"Read file {file_path} ({len(content)} bytes) with "
            f"{len(dependencies)} dependencies"
        )

        return ReadResult(
            file_path=file_path,
            content=content,
            injected_context=injected_context,
            warnings=warnings,
        )

    def _get_file_dependencies(self, file_path: str) -> List[Relationship]:
        """Get dependencies for a file from the relationship graph.

        Args:
            file_path: Path to query.

        Returns:
            List of relationships where file_path depends on other files.
        """
        # Query the graph for relationships where this file is the source
        return self._graph.get_dependencies(file_path)

    def _get_token_encoder(self) -> Optional[tiktoken.Encoding]:
        """Get or initialize the tiktoken encoder.

        Uses lazy initialization to avoid network calls in __init__.
        Falls back gracefully if tiktoken is unavailable.

        Returns:
            tiktoken.Encoding or None if unavailable.
        """
        if self._token_encoder is None:
            try:
                self._token_encoder = tiktoken.get_encoding("cl100k_base")
            except Exception as e:
                logger.warning(f"Failed to initialize tiktoken encoder: {e}")
                return None
        return self._token_encoder

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken.

        Per TDD Section 3.8.4, uses cl100k_base encoding for accurate
        token counting matching Claude's tokenization.

        Falls back to word-based approximation if tiktoken is unavailable.

        Args:
            text: Text to count tokens for.

        Returns:
            Number of tokens in text (approximate if tiktoken unavailable).
        """
        encoder = self._get_token_encoder()
        if encoder is not None:
            return len(encoder.encode(text))

        # Fallback: approximate token count based on whitespace splitting
        # This is less accurate but allows operation without network
        if not text:
            return 0
        # Rough approximation: ~1.3 tokens per word for code
        words = len(text.split())
        return int(words * 1.3)

    def _get_symbol_usage_count(self, target_file: str, target_symbol: Optional[str]) -> int:
        """Get the number of files that use a specific symbol.

        Per FR-19, tracks how many files depend on each function/symbol
        for high-usage detection.

        Args:
            target_file: File containing the symbol.
            target_symbol: Symbol name (function/class). If None, counts all
                          dependencies on the target file.

        Returns:
            Number of unique files that use this symbol.
        """
        if not target_symbol:
            # Count unique files that depend on target_file for any symbol
            dependents = self._graph.get_dependents(target_file)
            return len({rel.source_file for rel in dependents})

        # Count unique files that specifically use this symbol
        all_relationships = self._graph.get_all_relationships()
        using_files: Set[str] = set()

        for rel in all_relationships:
            if rel.target_file == target_file and rel.target_symbol == target_symbol:
                using_files.add(rel.source_file)

        return len(using_files)

    def _get_high_usage_symbols(
        self, dependencies: List[Relationship]
    ) -> Dict[Tuple[str, str], int]:
        """Identify high-usage symbols from dependencies.

        Per FR-19/FR-20, identifies functions used in 3+ files
        (configurable via function_usage_warning_threshold).

        Args:
            dependencies: List of relationships to check.

        Returns:
            Dict mapping (target_file, target_symbol) to usage count
            for symbols meeting the threshold.
        """
        threshold = self.config.function_usage_warning_threshold
        high_usage: Dict[Tuple[str, str], int] = {}

        # Check each unique symbol in dependencies
        seen_symbols: Set[Tuple[str, Optional[str]]] = set()
        for rel in dependencies:
            symbol_key = (rel.target_file, rel.target_symbol)
            if symbol_key in seen_symbols:
                continue
            seen_symbols.add(symbol_key)

            if rel.target_symbol:
                usage_count = self._get_symbol_usage_count(rel.target_file, rel.target_symbol)
                if usage_count >= threshold:
                    high_usage[(rel.target_file, rel.target_symbol)] = usage_count

        return high_usage

    def _prioritize_dependencies(self, dependencies: List[Relationship]) -> List[Relationship]:
        """Prioritize dependencies for context injection.

        Priority order (per TDD Section 3.8.2):
        1. Direct dependencies over transitive
        2. Recently edited files (last 10 min)
        3. High usage frequency (3+ files - FR-19/FR-20)
        4. Relationship type: IMPORT > FUNCTION_CALL > INHERITANCE

        Args:
            dependencies: List of relationships to prioritize.

        Returns:
            Prioritized list of relationships.
        """
        type_priority = {
            RelationshipType.IMPORT: 0,
            RelationshipType.FUNCTION_CALL: 1,
            RelationshipType.CLASS_INHERITANCE: 2,
            RelationshipType.WILDCARD_IMPORT: 3,
            RelationshipType.CONDITIONAL_IMPORT: 4,
        }

        # Pre-compute high-usage symbols for efficiency
        high_usage_symbols = self._get_high_usage_symbols(dependencies)

        def sort_key(rel: Relationship) -> Tuple[int, int, int, int, int]:
            # Lower values = higher priority

            # 1. Check if target file was recently modified (last 10 min)
            timestamp = self._file_watcher.get_timestamp(rel.target_file)
            if timestamp:
                age_minutes = (time.time() - timestamp) / 60
                recently_edited = 0 if age_minutes < 10 else 1
            else:
                recently_edited = 1  # Not tracked = lower priority

            # 2. High usage frequency - functions used in 3+ files get priority
            symbol_key = (rel.target_file, rel.target_symbol)
            high_usage = 0 if rel.target_symbol and symbol_key in high_usage_symbols else 1

            # 3. Relationship type priority
            rel_type_priority = type_priority.get(rel.relationship_type, 99)

            return (recently_edited, high_usage, rel_type_priority, rel.line_number, 0)

        return sorted(dependencies, key=sort_key)

    def _get_function_signature(
        self, file_path: str, target_symbol: Optional[str], target_line: Optional[int]
    ) -> Optional[str]:
        """Extract function/class signature from a file.

        Args:
            file_path: Path to file containing the symbol.
            target_symbol: Name of function/class to find.
            target_line: Line number where symbol is defined.

        Returns:
            Signature string or None if not found.
        """
        if not target_line:
            return None

        try:
            # Try to get from cache first
            lines_context = 10  # Get up to 10 lines for signature
            line_range = (target_line, target_line + lines_context)

            content = self.cache.get(file_path, line_range)
            lines = content.splitlines()

            # Find the signature line (def/class)
            signature_lines: List[str] = []
            in_signature = False

            for line in lines:
                stripped = line.strip()
                if stripped.startswith(("def ", "class ", "async def ")):
                    in_signature = True
                    signature_lines.append(line.rstrip())
                    # Check if signature is complete (ends with :)
                    if stripped.endswith(":"):
                        break
                elif in_signature:
                    # Continuation of multi-line signature
                    signature_lines.append(line.rstrip())
                    if stripped.endswith(":"):
                        break

            if signature_lines:
                return "\n".join(signature_lines)

        except OSError as e:
            logger.debug(f"Could not read signature from {file_path}: {e}")

        return None

    def _assemble_context(
        self, target_file: str, dependencies: List[Relationship]
    ) -> Tuple[str, List[str]]:
        """Assemble context snippets from dependencies.

        Implements context assembly from TDD Section 3.8.3 and 3.8.4.
        Includes high-usage function warnings (FR-19, FR-20) and token metrics.

        Args:
            target_file: File being read.
            dependencies: List of dependencies to include.

        Returns:
            Tuple of (formatted_context, warnings).
        """
        warnings: List[str] = []

        if not dependencies:
            return "", warnings

        # Prioritize dependencies
        prioritized = self._prioritize_dependencies(dependencies)

        # Identify high-usage symbols for warnings (FR-19, FR-20)
        high_usage_symbols = self._get_high_usage_symbols(dependencies)

        # Group by target file for summary
        files_imported: Dict[str, List[Relationship]] = {}
        for rel in prioritized:
            if rel.target_file not in files_imported:
                files_imported[rel.target_file] = []
            files_imported[rel.target_file].append(rel)

        # Build context sections
        context_parts: List[str] = []
        context_parts.append("[Cross-File Context]")
        context_parts.append("")

        # Dependency summary
        context_parts.append("This file imports from:")
        for target_file_path, rels in files_imported.items():
            symbols = []
            for rel in rels:
                if rel.target_symbol:
                    symbols.append(f"{rel.target_symbol}() (line {rel.line_number})")
                else:
                    symbols.append(f"(line {rel.line_number})")
            symbols_str = ", ".join(symbols[:3])  # Limit to 3 per file
            if len(symbols) > 3:
                symbols_str += f" (+{len(symbols) - 3} more)"
            context_parts.append(f"- {Path(target_file_path).name}: {symbols_str}")

        context_parts.append("")

        # Recent definitions section
        context_parts.append("Recent definitions:")
        context_parts.append("")

        snippets_added = 0
        max_snippets = 10  # Reasonable limit per file
        warned_symbols: Set[Tuple[str, str]] = set()  # Track symbols we've warned about

        for rel in prioritized:
            if snippets_added >= max_snippets:
                break

            # Get signature for this dependency
            signature = self._get_function_signature(
                rel.target_file, rel.target_symbol, rel.target_line
            )

            if signature:
                context_parts.append(f"From {Path(rel.target_file).name}:{rel.target_line or '?'}")
                context_parts.append(signature)

                # Add implementation pointer
                context_parts.append(
                    f"    # Implementation in {Path(rel.target_file).name}:{rel.target_line or '?'}"
                )
                context_parts.append("")
                snippets_added += 1

                # Check for high-usage function warning (FR-19, FR-20)
                if rel.target_symbol:
                    symbol_key = (rel.target_file, rel.target_symbol)
                    if symbol_key in high_usage_symbols and symbol_key not in warned_symbols:
                        usage_count = high_usage_symbols[symbol_key]
                        warnings.append(
                            f"⚠️ Note: `{rel.target_symbol}()` is used in {usage_count} files"
                        )
                        warned_symbols.add(symbol_key)

            # Check for wildcard imports (EC-4)
            if rel.relationship_type == RelationshipType.WILDCARD_IMPORT:
                context_parts.append(f"From {Path(rel.target_file).name}:{rel.line_number}")
                context_parts.append(f"from {Path(rel.target_file).stem} import *")
                context_parts.append(
                    "    # Note: Wildcard import - specific function tracking unavailable"
                )
                target_name = Path(rel.target_file).name
                context_parts.append(f"    # See {target_name} for available functions")
                context_parts.append("")
                snippets_added += 1

                if self.config.warn_on_wildcards:
                    warnings.append(
                        f"⚠️ Wildcard import from {rel.target_file} at line {rel.line_number}"
                    )

        context_parts.append("---")

        # Assemble final context
        context_text = "\n".join(context_parts)

        # Log token count for metrics (TDD Section 3.8.4)
        # v0.1.0: No limit, gather data on actual token counts
        token_count = self._count_tokens(context_text)
        logger.debug(
            f"Context injection for {target_file}: "
            f"{len(prioritized)} dependencies, {snippets_added} snippets, {token_count} tokens"
        )

        return context_text, warnings

    def get_relationship_graph(self) -> GraphExport:
        """Get the full relationship graph for export.

        Returns:
            GraphExport object with current graph state (FR-23, FR-25).
        """
        return self.store.export_graph()

    def get_dependents(self, file_path: str) -> List[Dict[str, Any]]:
        """Get files that depend on the given file.

        Args:
            file_path: Path to file to query.

        Returns:
            List of relationship dictionaries for files that import from file_path.
        """
        self._validate_filepath(file_path)
        relationships = self._graph.get_dependents(file_path)
        return [rel.to_dict() for rel in relationships]

    def get_dependencies(self, file_path: str) -> List[Dict[str, Any]]:
        """Get files that the given file depends on.

        Args:
            file_path: Path to file to query.

        Returns:
            List of relationship dictionaries for files that file_path imports from.
        """
        self._validate_filepath(file_path)
        relationships = self._graph.get_dependencies(file_path)
        return [rel.to_dict() for rel in relationships]

    def get_graph_statistics(self) -> Dict[str, Any]:
        """Get statistics about the relationship graph.

        Returns:
            Dictionary with graph statistics.
        """
        graph_export = self._graph.export_to_dict()
        statistics: Dict[str, Any] = graph_export.get("statistics", {})
        return statistics

    def invalidate_cache(self, file_path: Optional[str] = None) -> None:
        """Invalidate cache entries.

        Args:
            file_path: Path to invalidate. If None, clears entire cache.
        """
        if file_path:
            self._validate_filepath(file_path)
            self.cache.invalidate(file_path)
        else:
            self.cache.clear()

    def shutdown(self) -> None:
        """Shutdown the service and cleanup resources.

        Stops file watcher, clears cache, and releases resources.
        """
        logger.info("CrossFileContextService shutting down...")

        # Stop file watcher
        self.stop_file_watcher()

        # Clear cache
        self.cache.clear()

        # Clear graph
        self._graph.clear()

        logger.info("CrossFileContextService shutdown complete")
