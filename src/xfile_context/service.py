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

from xfile_context.analyzers.python_analyzer import PythonAnalyzer
from xfile_context.cache import WorkingMemoryCache
from xfile_context.config import Config
from xfile_context.detectors import (
    ClassInheritanceDetector,
    ConditionalImportDetector,
    DecoratorDetector,
    DetectorRegistry,
    DynamicDispatchDetector,
    ExecEvalDetector,
    FunctionCallDetector,
    FunctionDefinitionDetector,
    ImportDetector,
    MetaclassDetector,
    MonkeyPatchingDetector,
    WildcardImportDetector,
)
from xfile_context.file_watcher import FileWatcher
from xfile_context.graph_updater import GraphUpdater
from xfile_context.injection_logger import (
    InjectionEvent,
    InjectionLogger,
    InjectionStatistics,
    get_recent_injections,
)
from xfile_context.metrics_collector import MetricsCollector, SessionMetrics
from xfile_context.models import Relationship, RelationshipGraph, RelationshipType
from xfile_context.relationship_builder import RelationshipBuilder
from xfile_context.staleness_resolver import StalenessResolver
from xfile_context.storage import GraphExport, InMemoryStore, RelationshipStore
from xfile_context.symbol_cache import SymbolDataCache
from xfile_context.warning_formatter import StructuredWarning, WarningEmitter

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
        injection_logger: Optional[InjectionLogger] = None,
        metrics_collector: Optional[MetricsCollector] = None,
        session_id: Optional[str] = None,
        data_root: Optional[Path] = None,
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
            injection_logger: InjectionLogger instance (default: creates new logger)
            metrics_collector: MetricsCollector instance (default: creates new collector)
            session_id: Session ID for log filenames (Issue #150). If None, loggers
                       use legacy static filenames.
            data_root: Root directory for logs (Issue #150). If None, loggers use
                      ~/.cross_file_context/ by default.
        """
        self._session_id = session_id
        self._data_root = data_root
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
        self._detector_registry.register(FunctionDefinitionDetector())
        self._detector_registry.register(ClassInheritanceDetector())

        # Register dynamic pattern detectors (TDD Section 3.5.4, Section 3.9.1)
        # These detect patterns that cannot be statically analyzed (FR-42 fail-safe)
        project_root_str = str(self._project_root)
        self._detector_registry.register(DynamicDispatchDetector(project_root_str))
        self._detector_registry.register(MonkeyPatchingDetector(project_root_str))
        self._detector_registry.register(ExecEvalDetector(project_root_str))
        self._detector_registry.register(DecoratorDetector(project_root_str))
        self._detector_registry.register(MetaclassDetector(project_root_str))

        # Initialize analyzer
        self._analyzer = (
            analyzer
            if analyzer is not None
            else PythonAnalyzer(
                graph=self._graph,
                detector_registry=self._detector_registry,
            )
        )

        # Track if watcher is running
        self._watcher_running = False

        # Initialize tiktoken encoder for token counting (TDD Section 3.8.4)
        # Use cl100k_base encoding (compatible with Claude/GPT-4)
        # Lazy initialization to avoid network calls in __init__
        self._token_encoder: Optional[tiktoken.Encoding] = None

        # Initialize warning emitter for dynamic pattern warnings (TDD Section 3.9.3)
        self._warning_emitter = WarningEmitter()

        # Initialize injection logger for context injection event logging (TDD Section 3.8.5)
        # Per FR-26: Log all context injections for analysis
        # Issue #150: Use session_id and data_root for new log architecture
        self._injection_logger = (
            injection_logger
            if injection_logger is not None
            else InjectionLogger(
                session_id=self._session_id,
                data_root=self._data_root,
            )
        )

        # Initialize metrics collector for session metrics (TDD Section 3.10.1)
        # Per FR-43: Emit metrics at session end
        # Issue #150: Use session_id and data_root for new log architecture
        self._metrics_collector = (
            metrics_collector
            if metrics_collector is not None
            else MetricsCollector(
                session_id=self._session_id,
                data_root=self._data_root,
            )
        )

        # Capture configuration values in metrics per FR-49
        self._metrics_collector.set_configuration(
            {
                "cache_expiry_minutes": config.cache_expiry_minutes,
                "cache_size_limit_kb": config.cache_size_limit_kb,
                "context_token_limit": config.context_token_limit,
                "function_usage_warning_threshold": config.function_usage_warning_threshold,
                "warn_on_wildcards": config.warn_on_wildcards,
                "enable_context_injection": config.enable_context_injection,
            }
        )

        # Initialize warning logger for warning event logging (TDD Section 3.9.5)
        # Issue #150: Use session_id and data_root for new log architecture
        from xfile_context.warning_logger import WarningLogger

        self._warning_logger = WarningLogger(
            session_id=self._session_id,
            data_root=self._data_root,
        )

        # Initialize RelationshipBuilder for two-phase analysis (Issue #125)
        # The builder is shared across files for cross-file symbol resolution
        # Note: Two-phase analysis is always enabled (Issue #133 fix requirement)
        self._relationship_builder = RelationshipBuilder()

        # Initialize SymbolDataCache for incremental analysis (Issue #125 Phase 3)
        # Note: Symbol caching is always enabled (Issue #133 fix requirement)
        self._symbol_cache = SymbolDataCache(
            max_entries=self.config.symbol_cache_max_entries,
        )
        logger.info(f"Symbol cache enabled (max {self.config.symbol_cache_max_entries} entries)")

        # Initialize graph updater (after RelationshipBuilder for two-phase support)
        self._graph_updater = (
            graph_updater
            if graph_updater is not None
            else GraphUpdater(
                graph=self._graph,
                analyzer=self._analyzer,
                file_watcher=self._file_watcher,
                relationship_builder=self._relationship_builder,
            )
        )

        logger.info(f"CrossFileContextService initialized with project_root={self._project_root}")

    def _needs_analysis(self, file_path: str) -> bool:
        """Check if file needs (re-)analysis.

        Returns True if:
        - File exists AND has never been analyzed (no metadata)
        - File exists AND was modified since last analysis (mtime > last_analyzed)

        Returns False if:
        - File doesn't exist
        - File was already analyzed and not modified

        This enables lazy initialization per Issue #114: files are analyzed
        on-demand when read_file_with_context is called, rather than requiring
        eager full-project analysis at startup.

        Args:
            file_path: Path to file to check.

        Returns:
            True if file needs analysis, False otherwise.
        """
        # Check if file exists first
        path = Path(file_path)
        if not path.exists():
            return False  # Non-existent file doesn't need analysis

        metadata = self._graph.get_file_metadata(file_path)

        if metadata is None:
            return True  # File exists but never analyzed

        # Check if file was modified since last analysis
        try:
            file_mtime = path.stat().st_mtime
            if file_mtime > metadata.last_analyzed:
                return True  # Modified since last analysis
        except OSError:
            return False  # Can't stat file, skip

        return False  # Already analyzed and not modified

    def _resolve_staleness(self, file_path: str) -> None:
        """Resolve staleness for target file and its transitive dependencies.

        Implements Issue #117 Option B: Full transitive dependency check using
        topological sort-based staleness resolution.

        This method ensures that:
        1. The target file is analyzed if stale
        2. All transitive dependencies are checked for staleness
        3. Stale files are processed in topological order (dependencies first)
        4. Files with pending relationships have them rebuilt from symbol data

        Issue #133 Fix:
        The StalenessResolver now accepts a RelationshipBuilder to rebuild
        relationships for pending files from their FileSymbolData. This is
        cleaner than the previous store/restore approach and handles all
        edge cases correctly.

        Args:
            file_path: Target file being read via read_file_with_context().
        """
        # Create staleness resolver with callbacks to service methods
        # Pass the RelationshipBuilder for Issue #133 fix
        resolver = StalenessResolver(
            graph=self._graph,
            needs_analysis=self._needs_analysis,
            analyze_file=self._analyze_file_for_staleness,
            relationship_builder=self._relationship_builder,
        )

        # Resolve staleness for target and all transitive dependencies
        resolver.resolve_staleness(file_path)

    def _analyze_file_for_staleness(self, file_path: str) -> bool:
        """Analyze a file during staleness resolution (Issue #117 Option B).

        This is a callback used by StalenessResolver to analyze stale files.
        Uses two-phase analysis (always enabled per Issue #133 fix requirement).

        Args:
            file_path: File to analyze.

        Returns:
            True if analysis succeeded, False otherwise.
        """
        logger.debug(f"Staleness resolution: analyzing {file_path}")

        return self._analyzer.analyze_file_two_phase(
            file_path, relationship_builder=self._relationship_builder
        )

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

        Uses two-phase analysis (always enabled per Issue #133 fix requirement):
        Phase 1: AST -> FileSymbolData (extract symbols)
        Phase 2: FileSymbolData -> Relationships (via RelationshipBuilder)

        Args:
            file_path: Path to Python file to analyze.

        Returns:
            True if analysis succeeded, False otherwise.
        """
        self._validate_filepath(file_path)

        # Two-phase analysis: AST -> FileSymbolData -> Relationships
        result = self._analyzer.analyze_file_two_phase(
            file_path, relationship_builder=self._relationship_builder
        )

        # Collect warnings from dynamic pattern detectors
        self._collect_detector_warnings()

        return result

    def analyze_directory(self, directory_path: Optional[str] = None) -> Dict[str, Any]:
        """Analyze all Python files in a directory.

        Uses two-phase analysis (always enabled per Issue #133 fix requirement):
        1. Extracting symbol data from all files first
        2. Building relationships with full project context

        This provides better cross-file resolution than analyzing files independently.

        Args:
            directory_path: Path to directory (default: project_root).

        Returns:
            Statistics about analyzed files.
        """
        dir_path = Path(directory_path) if directory_path else self._project_root

        stats: Dict[str, Any] = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "elapsed_ms": 0.0,
        }

        start_time = time.time()

        # Collect files to analyze
        files_to_analyze: List[str] = []
        for py_file in dir_path.rglob("*.py"):
            file_path = str(py_file)

            # Check if file should be ignored
            if self._file_watcher.should_ignore(file_path):
                stats["skipped"] += 1
                continue

            files_to_analyze.append(file_path)
            stats["total"] += 1

        # Two-phase analysis: Extract all symbols first, then build relationships
        # This provides better cross-file resolution
        # Pass symbol cache for incremental analysis (Issue #125 Phase 3)
        success, failed, self._relationship_builder = self._analyzer.analyze_project_two_phase(
            files_to_analyze,
            relationship_builder=self._relationship_builder,
            symbol_cache=self._symbol_cache,
        )
        stats["success"] = success
        stats["failed"] = failed
        # Add cache statistics
        cache_stats = self._symbol_cache.get_statistics()
        stats["cache_hits"] = cache_stats["hits"]
        stats["cache_hit_rate"] = cache_stats["hit_rate"]

        stats["elapsed_ms"] = (time.time() - start_time) * 1000

        # Collect warnings from dynamic pattern detectors
        self._collect_detector_warnings()

        logger.info(
            f"Analyzed {stats['total']} files (two-phase) in {stats['elapsed_ms']:.1f}ms: "
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

        # Lazy initialization: analyze target file and stale dependencies (Issue #114, #117)
        # This ensures context is available on first read without requiring
        # eager full-project analysis at startup.
        #
        # Issue #117 Option B: Use topological sort-based staleness resolution
        # to handle transitive dependencies correctly. This ensures:
        # - Modified dependency files are re-analyzed before their dependents
        # - Files with pending relationships are restored in correct order
        # - Diamond patterns and complex dependency chains are handled properly
        self._resolve_staleness(file_path)

        # Get dependencies for this file from the graph
        dependencies = self._get_file_dependencies(file_path)

        if dependencies:
            # Assemble and format context
            injected_context, context_warnings = self._assemble_context(file_path, dependencies)
            warnings.extend(context_warnings)

        logger.debug(
            f"Read file {file_path} ({len(content)} bytes) with {len(dependencies)} dependencies"
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

        # Cache all relationships once to avoid O(N×M) complexity
        all_relationships = self._graph.get_all_relationships()

        # Check each unique symbol in dependencies
        seen_symbols: Set[Tuple[str, Optional[str]]] = set()
        for rel in dependencies:
            symbol_key = (rel.target_file, rel.target_symbol)
            if symbol_key in seen_symbols:
                continue
            seen_symbols.add(symbol_key)

            if rel.target_symbol:
                # Count directly using cached relationships
                using_files = {
                    r.source_file
                    for r in all_relationships
                    if r.target_file == rel.target_file and r.target_symbol == rel.target_symbol
                }
                usage_count = len(using_files)
                if usage_count >= threshold:
                    high_usage[(rel.target_file, rel.target_symbol)] = usage_count

        return high_usage

    def _prioritize_dependencies(self, dependencies: List[Relationship]) -> List[Relationship]:
        """Prioritize dependencies for context injection.

        Returns a new sorted list without modifying the input.

        Priority order (per TDD Section 3.8.2):
        1. Recently edited files (last 10 min)
        2. High usage frequency (3+ files - FR-19/FR-20)
        3. Relationship type: IMPORT > FUNCTION_CALL > INHERITANCE
        4. Line number (earlier lines first)

        Note: "Direct dependencies over transitive" from TDD 3.8.2 is not
        implemented in v0.1.0 as the graph doesn't track transitivity.

        Args:
            dependencies: List of relationships to prioritize.

        Returns:
            New list of relationships sorted by priority (highest first).
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

        def sort_key(rel: Relationship) -> Tuple[int, int, int, int]:
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

            return (recently_edited, high_usage, rel_type_priority, rel.line_number)

        return sorted(dependencies, key=sort_key)

    def _get_function_line_count(self, file_path: str, start_line: int) -> Optional[int]:
        """Get the number of lines in a function definition.

        Per EC-12, used to detect large functions (200+ lines) that need
        truncation notes in context injection.

        Args:
            file_path: Path to file containing the function.
            start_line: Line number where function definition starts.

        Returns:
            Number of lines in the function, or None if cannot be determined.
        """
        try:
            # Read enough lines to capture the function (max 500 for reasonable bound)
            max_lines = 500
            line_range = (start_line, start_line + max_lines)
            content = self.cache.get(file_path, line_range)
            lines = content.splitlines()

            if not lines:
                return None

            # Find the indentation of the function definition
            first_line = lines[0]
            base_indent = len(first_line) - len(first_line.lstrip())

            # Count lines until we find a line at the same or lower indentation
            # (excluding blank lines and comments at the start)
            line_count = 1

            for line in lines[1:]:
                line_count += 1
                stripped = line.strip()

                # Skip blank lines
                if not stripped:
                    continue

                # Check if we've exited the function
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= base_indent and stripped and not stripped.startswith("#"):
                    # We've found a line at the same or lower indentation
                    # This marks the end of the function
                    return line_count - 1  # Don't count the line outside

            # If we reached the end, return the count
            return line_count

        except OSError:
            return None

    def _get_function_signature_with_docstring(
        self, file_path: str, target_symbol: Optional[str], target_line: Optional[int]
    ) -> Tuple[Optional[str], Optional[str], Optional[Tuple[int, int]]]:
        """Extract function/class signature with optional docstring.

        Per TDD Section 3.8.3, includes:
        - Function signature (def/class line)
        - Short docstring (<50 chars) if present
        - Line range for implementation pointer

        Args:
            file_path: Path to file containing the symbol.
            target_symbol: Name of function/class to find.
            target_line: Line number where symbol is defined.

        Returns:
            Tuple of (signature, docstring, line_range):
            - signature: The def/class signature or None if not found
            - docstring: Short docstring (<50 chars) or None
            - line_range: (start_line, end_line) tuple or None
        """
        if not target_line:
            return None, None, None

        try:
            # Read more lines to capture signature + docstring + some body
            lines_context = 20
            line_range = (target_line, target_line + lines_context)

            content = self.cache.get(file_path, line_range)
            lines = content.splitlines()

            # Find the signature line (def/class)
            signature_lines: List[str] = []
            in_signature = False
            signature_end_idx = 0

            for idx, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith(("def ", "class ", "async def ")):
                    in_signature = True
                    signature_lines.append(line.rstrip())
                    if stripped.endswith(":"):
                        signature_end_idx = idx
                        break
                elif in_signature:
                    signature_lines.append(line.rstrip())
                    if stripped.endswith(":"):
                        signature_end_idx = idx
                        break

            if not signature_lines:
                return None, None, None

            signature = "\n".join(signature_lines)

            # Look for docstring after signature
            docstring = None
            if signature_end_idx + 1 < len(lines):
                next_line = lines[signature_end_idx + 1].strip()
                # Check for docstring (single-line only for brevity)
                if next_line.startswith(('"""', "'''")):
                    quote = next_line[:3]
                    if next_line.endswith(quote) and len(next_line) > 6:
                        # Single-line docstring
                        doc_content = next_line[3:-3].strip()
                        if len(doc_content) < 50:  # Per TDD 3.8.3: <50 chars
                            docstring = doc_content

            # Calculate line range for this function
            func_line_count = self._get_function_line_count(file_path, target_line)
            if func_line_count:
                impl_range = (target_line, target_line + func_line_count - 1)
            else:
                impl_range = (target_line, target_line)

            return signature, docstring, impl_range

        except OSError as e:
            logger.debug(f"Could not read signature from {file_path}: {e}")

        return None, None, None

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
        signature, _, _ = self._get_function_signature_with_docstring(
            file_path, target_symbol, target_line
        )
        return signature

    def _get_cache_age_minutes(self, file_path: str) -> Optional[float]:
        """Get the cache age for a file in minutes.

        Per TDD Section 3.8.3, used for "last read: X minutes ago" indicator.

        Args:
            file_path: Path to file to check.

        Returns:
            Age in minutes, or None if not cached.
        """
        # Check file watcher timestamps for last known access time
        timestamp = self._file_watcher.get_timestamp(file_path)
        if timestamp:
            age_minutes = (time.time() - timestamp) / 60
            return age_minutes
        return None

    def _check_deleted_files(self, dependencies: List[Relationship]) -> Tuple[List[str], Set[str]]:
        """Check for dependencies on deleted files.

        Per EC-14, detects when target files have been deleted and
        generates appropriate warnings.

        Excludes special marker paths (<stdlib:...>, <third-party:...>,
        <builtin:...>, <unresolved:...>) from file existence checks since
        these are not actual filesystem paths.

        Args:
            dependencies: List of relationships to check.

        Returns:
            Tuple of (warning_messages, deleted_file_paths).
        """
        warnings: List[str] = []
        deleted_files: Set[str] = set()

        for rel in dependencies:
            # Skip special marker paths (stdlib, third-party, builtin, unresolved)
            # These are not actual filesystem paths and should not be checked
            if rel.target_file.startswith("<") and rel.target_file.endswith(">"):
                continue

            target_path = Path(rel.target_file)

            # Check if file is marked as deleted in metadata
            metadata = self._graph.get_file_metadata(rel.target_file)
            if metadata and metadata.deleted:
                if rel.target_file not in deleted_files:
                    deleted_files.add(rel.target_file)
                    # Format deletion time if available
                    if metadata.deletion_time:
                        from datetime import datetime

                        deletion_dt = datetime.fromtimestamp(metadata.deletion_time)
                        deletion_str = deletion_dt.strftime("%Y-%m-%d %H:%M")
                        warnings.append(
                            f"⚠️ Note: This file imports from {target_path.name} "
                            f"which was deleted on {deletion_str}"
                        )
                    else:
                        warnings.append(
                            f"⚠️ Note: This file imports from {target_path.name} which was deleted"
                        )
            # Also check if file physically exists
            elif not target_path.exists() and rel.target_file not in deleted_files:
                deleted_files.add(rel.target_file)
                warnings.append(
                    f"⚠️ Note: This file imports from {target_path.name} which no longer exists"
                )

        return warnings, deleted_files

    def _log_injection_event(
        self,
        rel: Relationship,
        target_file: str,
        snippet: str,
        snippet_location: str,
        token_count: int,
        context_token_total: int,
    ) -> None:
        """Log a context injection event per TDD Section 3.8.5.

        Creates and logs an InjectionEvent with all required fields per FR-27.
        Events are flushed immediately to ensure durability.

        Args:
            rel: The relationship being injected.
            target_file: File being read (where context is injected).
            snippet: The injected content (signature + docstring).
            snippet_location: File path and line range of snippet.
            token_count: Token count of this single snippet.
            context_token_total: Cumulative token count for all snippets.
        """
        # Get cache age in seconds (convert from minutes)
        cache_age_minutes = self._get_cache_age_minutes(rel.target_file)
        cache_age_seconds = cache_age_minutes * 60 if cache_age_minutes is not None else None

        # Determine if this was a cache hit (has timestamp = was cached)
        cache_hit = cache_age_minutes is not None

        # Get relationship type as string (handle both enum and string)
        rel_type = rel.relationship_type
        rel_type_str = rel_type.value if hasattr(rel_type, "value") else str(rel_type)

        # Create the injection event
        event = InjectionEvent.create(
            source_file=rel.target_file,
            target_file=target_file,
            relationship_type=rel_type_str,
            snippet=snippet,
            snippet_location=snippet_location,
            cache_age_seconds=cache_age_seconds,
            cache_hit=cache_hit,
            token_count=token_count,
            context_token_total=context_token_total,
        )

        # Log the event (immediately flushed per TDD 3.8.5)
        self._injection_logger.log_injection(event)

    def _assemble_context(
        self, target_file: str, dependencies: List[Relationship]
    ) -> Tuple[str, List[str]]:
        """Assemble context snippets from dependencies.

        Implements context assembly from TDD Section 3.8.3 and 3.8.4.
        Format includes:
        - Header: [Cross-File Context]
        - Cache age indicator (last read: X minutes ago)
        - Dependency summary
        - Recent definitions with signatures and docstrings
        - Implementation line ranges
        - Special cases: wildcards (EC-4), large functions (EC-12), deleted files (EC-14)
        - High-usage function warnings (FR-19, FR-20)

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

        # Check for deleted files (EC-14)
        deleted_warnings, deleted_files = self._check_deleted_files(dependencies)
        warnings.extend(deleted_warnings)

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
        # Per TDD Section 3.8.3 and FR-13: Line numbers should indicate where
        # symbols are DEFINED in the dependency file, not where they're USED
        # in the target file. This enables efficient snippet-based caching.
        # Issue #136: Clarify that line numbers refer to dependency files
        context_parts.append("This file imports from (line numbers are in dependency files):")
        # Sort references by file path for deterministic output (Issue #131)
        for target_file_path in sorted(files_imported.keys()):
            rels = files_imported[target_file_path]
            symbols = []
            for rel in rels:
                if rel.target_symbol:
                    # Use target_line (definition line) instead of line_number (usage line)
                    if rel.target_line is not None:
                        symbols.append(f"{rel.target_symbol}() (line {rel.target_line})")
                    else:
                        # Fallback if target_line not available
                        symbols.append(f"{rel.target_symbol}()")
                else:
                    symbols.append(f"(line {rel.line_number})")
            # Sort and deduplicate symbols for deterministic output (Issue #131, #136)
            unique_symbols = sorted(set(symbols))
            # Print all symbols without truncation (Issue #131)
            symbols_str = ", ".join(unique_symbols)
            # Issue #136: Use full file path instead of just filename
            context_parts.append(f"- {target_file_path}: {symbols_str}")

        context_parts.append("")

        # Calculate overall cache age (use oldest cached dependency)
        cache_ages = []
        for rel in prioritized:
            age = self._get_cache_age_minutes(rel.target_file)
            if age is not None:
                cache_ages.append(age)

        # Recent definitions section with cache age indicator (TDD 3.8.3)
        if cache_ages:
            max_age = max(cache_ages)
            if max_age < 1:
                age_str = "just now"
            elif max_age < 60:
                age_str = f"{int(max_age)} minute{'s' if int(max_age) != 1 else ''} ago"
            else:
                hours = int(max_age / 60)
                age_str = f"{hours} hour{'s' if hours != 1 else ''} ago"
            context_parts.append(f"Recent definitions (last read: {age_str}):")
        else:
            context_parts.append("Recent definitions:")
        context_parts.append("")

        # Deduplicate relationships for recent definitions section (Issue #144)
        # This is assembly-level deduplication (complements graph-level deduplication in PR #145).
        # Key: (target_file, target_line, source_file, relationship_type)
        # Excludes usage line number because a single function definition
        # is sufficient for all usages in the file for now.
        seen_dedup_keys: Set[Tuple[str, Optional[int], str, str]] = set()
        deduplicated_rels: List[Relationship] = []
        for rel in prioritized:
            dedup_key = (
                rel.target_file,
                rel.target_line,
                rel.source_file,
                rel.relationship_type,
            )
            if dedup_key not in seen_dedup_keys:
                seen_dedup_keys.add(dedup_key)
                deduplicated_rels.append(rel)

        snippets_added = 0
        max_snippets = 10  # Reasonable limit per file
        warned_symbols: Set[Tuple[str, str]] = set()  # Track symbols we've warned about

        # Large function threshold (EC-12)
        large_function_threshold = 200

        # Track cumulative token count for injection logging (TDD Section 3.8.5)
        context_token_total = 0

        for rel in deduplicated_rels:
            if snippets_added >= max_snippets:
                break

            # Skip deleted files in snippet generation (EC-14)
            if rel.target_file in deleted_files:
                # Add a note about the deleted file
                # Issue #136: Use full file path
                snippet_text = f"# ⚠️ File was deleted\n# Last known location: {rel.target_file}"
                context_parts.append(f"From {rel.target_file}:{rel.line_number}")
                context_parts.append("    # ⚠️ File was deleted")
                context_parts.append(f"    # Last known location: {rel.target_file}")
                context_parts.append("")

                # Log the injection event (FR-26)
                snippet_token_count = self._count_tokens(snippet_text)
                context_token_total += snippet_token_count
                self._log_injection_event(
                    rel=rel,
                    target_file=target_file,
                    snippet=snippet_text,
                    snippet_location=f"{rel.target_file}:{rel.line_number}",
                    token_count=snippet_token_count,
                    context_token_total=context_token_total,
                )

                snippets_added += 1
                continue

            # Check for wildcard imports (EC-4)
            # Issue #136: Use full file path instead of just filename
            if rel.relationship_type == RelationshipType.WILDCARD_IMPORT:
                snippet_text = (
                    f"from {Path(rel.target_file).stem} import *\n"
                    f"# Note: Wildcard import - specific function tracking unavailable\n"
                    f"# See {rel.target_file} for available functions"
                )
                context_parts.append(f"From {rel.target_file}:{rel.line_number}")
                context_parts.append(f"from {Path(rel.target_file).stem} import *")
                context_parts.append(
                    "    # Note: Wildcard import - specific function tracking unavailable"
                )
                context_parts.append(f"    # See {rel.target_file} for available functions")
                context_parts.append("")

                # Log the injection event (FR-26)
                snippet_token_count = self._count_tokens(snippet_text)
                context_token_total += snippet_token_count
                self._log_injection_event(
                    rel=rel,
                    target_file=target_file,
                    snippet=snippet_text,
                    snippet_location=f"{rel.target_file}:{rel.line_number}",
                    token_count=snippet_token_count,
                    context_token_total=context_token_total,
                )

                snippets_added += 1

                if self.config.warn_on_wildcards:
                    warnings.append(
                        f"⚠️ Wildcard import from {rel.target_file} at line {rel.line_number}"
                    )
                continue

            # Get signature with docstring and line range
            signature, docstring, impl_range = self._get_function_signature_with_docstring(
                rel.target_file, rel.target_symbol, rel.target_line
            )

            if signature:
                # Issue #136: Use full file path instead of just filename
                context_parts.append(f"From {rel.target_file}:{rel.target_line or '?'}")
                context_parts.append(signature)

                # Build snippet text for logging
                snippet_parts = [signature]
                if docstring:
                    snippet_parts.append(f'"""{docstring}"""')

                # Add docstring if present and short (TDD 3.8.3: <50 chars)
                if docstring:
                    context_parts.append(f'    """{docstring}"""')

                # Calculate snippet location for logging
                if impl_range:
                    start_line, end_line = impl_range
                    snippet_location = f"{rel.target_file}:{start_line}-{end_line}"
                else:
                    start_line = rel.target_line or 0
                    end_line = start_line
                    snippet_location = f"{rel.target_file}:{rel.target_line or '?'}"

                # Check for large function (EC-12)
                if impl_range:
                    line_count = end_line - start_line + 1

                    if line_count >= large_function_threshold:
                        # Large function - add truncation note
                        context_parts.append(
                            f"    # Function is {line_count}+ lines, showing signature only"
                        )
                        context_parts.append(
                            f"    # Full definition: {rel.target_file}:{start_line}-{end_line}"
                        )
                    else:
                        # Normal function - show implementation range
                        context_parts.append(
                            f"    # Implementation in {rel.target_file}:{start_line}-{end_line}"
                        )
                else:
                    # Fallback if no range available
                    context_parts.append(
                        f"    # Implementation in {rel.target_file}:{rel.target_line or '?'}"
                    )

                context_parts.append("")

                # Log the injection event (FR-26)
                snippet_text = "\n".join(snippet_parts)
                snippet_token_count = self._count_tokens(snippet_text)
                context_token_total += snippet_token_count
                self._log_injection_event(
                    rel=rel,
                    target_file=target_file,
                    snippet=snippet_text,
                    snippet_location=snippet_location,
                    token_count=snippet_token_count,
                    context_token_total=context_token_total,
                )

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

        context_parts.append("---")

        # Assemble final context
        context_text = "\n".join(context_parts)

        # Log token count for metrics (TDD Section 3.8.4)
        # v0.1.0: No limit, gather data on actual token counts
        token_count = self._count_tokens(context_text)
        logger.debug(
            f"Context injection for {target_file}: "
            f"{len(prioritized)} dependencies ({len(deduplicated_rels)} unique), "
            f"{snippets_added} snippets, {token_count} tokens"
        )

        # Record token count for session metrics per FR-44
        exceeded_threshold = token_count > self.config.context_token_limit
        self._metrics_collector.record_injection_token_count(token_count, exceeded_threshold)

        return context_text, warnings

    def get_relationship_graph(self) -> GraphExport:
        """Get the full relationship graph for export.

        Returns the full graph export per TDD Section 3.10.3 with:
        - metadata: timestamp, version, language, project_root, counts
        - files: list of file info with absolute and relative paths
        - relationships: all detected relationships with full metadata
        - graph_metadata: circular imports, most connected files

        Returns:
            GraphExport object with current graph state (FR-23, FR-25).
        """
        return self._graph.export_to_dict(project_root=str(self._project_root))

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

    def _collect_detector_warnings(self) -> None:
        """Collect warnings from all dynamic pattern detectors.

        Called after analysis to gather warnings from detectors and add them
        to the warning emitter. Clears detector warnings after collection.
        """
        from xfile_context.detectors.dynamic_pattern_detector import DynamicPatternDetector

        for detector in self._detector_registry.get_detectors():
            if isinstance(detector, DynamicPatternDetector):
                warnings = detector.get_warnings()
                self._warning_emitter.add_warnings(warnings)
                detector.clear_warnings()

    def get_warnings(self, include_test_modules: bool = False) -> List[StructuredWarning]:
        """Get all collected dynamic pattern warnings.

        Returns structured warnings in FR-38 format from analysis.

        Args:
            include_test_modules: If True, include warnings from test modules.
                                  Default is False (suppressed per TDD Section 3.9.1).

        Returns:
            List of StructuredWarning objects.
        """
        return self._warning_emitter.get_warnings(include_test_modules=include_test_modules)

    def get_warnings_json(self, include_test_modules: bool = False, indent: int = 2) -> str:
        """Get all collected warnings as JSON.

        Returns warnings in machine-parseable JSON format per FR-38.

        Args:
            include_test_modules: If True, include warnings from test modules.
            indent: Indentation level for pretty printing.

        Returns:
            JSON string of warnings array.
        """
        return self._warning_emitter.to_json(
            include_test_modules=include_test_modules, indent=indent
        )

    def get_warnings_human_readable(self, include_test_modules: bool = False) -> str:
        """Get all collected warnings as human-readable text.

        Returns warnings in human-readable format per TDD Section 3.9.3.

        Args:
            include_test_modules: If True, include warnings from test modules.

        Returns:
            Human-readable string with all warnings.
        """
        return self._warning_emitter.to_human_readable(include_test_modules=include_test_modules)

    def get_warnings_by_file(
        self, file_path: str, include_test_modules: bool = False
    ) -> List[StructuredWarning]:
        """Get warnings for a specific file.

        Args:
            file_path: File path to filter by.
            include_test_modules: If True, include warnings from test modules.

        Returns:
            List of StructuredWarning objects for the specified file.
        """
        self._validate_filepath(file_path)
        return self._warning_emitter.get_warnings_by_file(
            file_path, include_test_modules=include_test_modules
        )

    def get_warning_summary(self, include_test_modules: bool = False) -> Dict[str, int]:
        """Get summary of warnings by type.

        Args:
            include_test_modules: If True, include warnings from test modules.

        Returns:
            Dictionary mapping pattern types to counts.
        """
        return self._warning_emitter.summary(include_test_modules=include_test_modules)

    def clear_warnings(self) -> None:
        """Clear all collected warnings."""
        self._warning_emitter.clear()

    def get_injection_statistics(self) -> InjectionStatistics:
        """Get injection statistics for session metrics.

        Returns aggregated data about context injections per TDD Section 3.8.5:
        - Total injection count
        - Count by relationship type
        - Top source files by injection count
        - Cache hit/miss statistics

        Returns:
            InjectionStatistics with aggregated data.
        """
        return self._injection_logger.get_statistics()

    def get_recent_injections(
        self, target_file: Optional[str] = None, limit: int = 10
    ) -> List[InjectionEvent]:
        """Get recent context injection events per FR-29.

        Provides programmatic access to recent injection events for debugging
        and understanding what context was provided to Claude.

        Args:
            target_file: If provided, only return events for this target file.
                        If None, returns all recent events.
            limit: Maximum number of events to return. Default is 10.

        Returns:
            List of InjectionEvent objects, most recent first.
        """
        if target_file:
            self._validate_filepath(target_file)
        log_path = self._injection_logger.get_log_path()
        return get_recent_injections(log_path, target_file, limit)

    def get_injection_log_path(self) -> Path:
        """Get the path to the injection log file.

        Returns:
            Path to the injections.jsonl file.
        """
        return self._injection_logger.get_log_path()

    def get_symbol_cache_statistics(self) -> Dict[str, Any]:
        """Get symbol cache statistics for monitoring.

        Returns statistics about the symbol cache including:
        - entries: Current number of cached files
        - max_entries: Maximum cache size
        - hits: Number of cache hits
        - misses: Number of cache misses
        - hit_rate: Cache hit rate (0.0 to 1.0)
        - invalidations: Number of cache invalidations

        Returns:
            Dictionary with cache statistics.
        """
        return self._symbol_cache.get_statistics()

    def get_session_metrics(self) -> SessionMetrics:
        """Get current session metrics without writing to file.

        Builds session metrics from all system components for inspection
        or intermediate analysis.

        Returns:
            SessionMetrics with current data from all subsystems.
        """
        return self._metrics_collector.build_session_metrics(
            cache=self.cache,
            injection_logger=self._injection_logger,
            warning_logger=self._warning_logger,
            graph=self._graph,
        )

    def get_metrics_log_path(self) -> Path:
        """Get the path to the session metrics log file.

        Returns:
            Path to the session_metrics.jsonl file.
        """
        return self._metrics_collector.get_log_path()

    def get_session_id(self) -> str:
        """Get the current session ID.

        Returns:
            Session ID string (UUID).
        """
        return self._metrics_collector.get_session_id()

    def shutdown(self) -> None:
        """Shutdown the service and cleanup resources.

        Stops file watcher, emits session metrics, clears cache, closes loggers,
        and releases resources. Per FR-43: Metrics are emitted at session end.
        """
        logger.info("CrossFileContextService shutting down...")

        # Stop file watcher
        self.stop_file_watcher()

        # Emit session metrics at session end per FR-43
        try:
            self._metrics_collector.finalize_and_write(
                cache=self.cache,
                injection_logger=self._injection_logger,
                warning_logger=self._warning_logger,
                graph=self._graph,
            )
        except Exception as e:
            logger.error(f"Failed to write session metrics: {e}")

        # Clear cache
        self.cache.clear()

        # Clear graph
        self._graph.clear()

        # Clear RelationshipBuilder (Issue #125)
        # This prevents memory accumulation in long-running sessions
        self._relationship_builder.clear()

        # Clear SymbolDataCache (Issue #125 Phase 3)
        self._symbol_cache.invalidate_all()

        # Close injection logger (ensures final flush)
        self._injection_logger.close()

        # Close warning logger
        self._warning_logger.close()

        logger.info("CrossFileContextService shutdown complete")
