# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Python AST analyzer for relationship extraction.

This module implements the AST parsing pipeline for Python files with:
- File reading with UTF-8/latin-1 fallback encoding
- File size limits (EC-17)
- AST parsing with error recovery (EC-18)
- Timeout and recursion depth limits
- Detector dispatch pattern (DD-1)
- Dynamic pattern detection and metadata aggregation (Section 3.5.4)

See TDD Section 3.5.1 for detailed specifications.
"""

import ast
import concurrent.futures
import logging
import time
from pathlib import Path
from typing import List, Optional, Set, Tuple

from xfile_context.detectors.dynamic_pattern_detector import DynamicPatternDetector
from xfile_context.detectors.registry import DetectorRegistry
from xfile_context.models import (
    FileMetadata,
    FileSymbolData,
    Relationship,
    RelationshipGraph,
    SymbolDefinition,
    SymbolReference,
)
from xfile_context.relationship_builder import RelationshipBuilder

logger = logging.getLogger(__name__)


class ASTParsingTimeoutError(Exception):
    """Raised when AST parsing exceeds timeout limit."""

    pass


class PythonAnalyzer:
    """AST-based analyzer for Python files.

    This analyzer implements the AST parsing pipeline (TDD Section 3.5.1):
    1. File Reading: UTF-8 with latin-1 fallback, file size limits
    2. AST Parsing: Python ast module with error recovery
    3. Detector Dispatch: Priority-based invocation of detector plugins
    4. Relationship Storage: Store results in RelationshipGraph

    Error Recovery (EC-18):
    - Syntax errors: Skip file, log warning, continue with other files
    - Encoding errors: Try UTF-8 first, fallback to latin-1
    - Import errors: Track relationship even if module doesn't exist
    - Partial analysis: Store results from successful detectors

    Performance Considerations:
    - Parse each file once, run all detectors on single AST traversal
    - Target: <200ms parsing time for files <5,000 lines (NFR-1)

    See TDD Section 3.4.2 for detailed specifications.
    """

    # Configuration constants (TDD Section 3.5.1)
    MAX_FILE_LINES = 10000  # EC-17: Skip files larger than this
    MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB: Prevent memory exhaustion from long lines
    AST_PARSING_TIMEOUT_SECONDS = 5  # Timeout for parsing a single file
    AST_MAX_RECURSION_DEPTH = 100  # Maximum AST traversal depth

    def __init__(
        self,
        graph: RelationshipGraph,
        detector_registry: DetectorRegistry,
        timeout_seconds: int = AST_PARSING_TIMEOUT_SECONDS,
        max_recursion_depth: int = AST_MAX_RECURSION_DEPTH,
        max_file_lines: int = MAX_FILE_LINES,
    ):
        """Initialize Python analyzer.

        Args:
            graph: RelationshipGraph to store detected relationships.
            detector_registry: Registry of detector plugins.
            timeout_seconds: Timeout for parsing a single file (default: 5).
            max_recursion_depth: Maximum AST traversal depth (default: 100).
            max_file_lines: Maximum file size in lines (default: 10000).
        """
        self.graph = graph
        self.detector_registry = detector_registry
        self.timeout_seconds = timeout_seconds
        self.max_recursion_depth = max_recursion_depth
        self.max_file_lines = max_file_lines

    def analyze_file(self, filepath: str) -> bool:
        """Analyze a Python file and extract relationships.

        This is the main entry point for file analysis. It implements the
        complete AST parsing pipeline from TDD Section 3.5.1.

        Args:
            filepath: Absolute path to Python file to analyze.

        Returns:
            True if analysis succeeded, False if file was skipped or failed.

        Side Effects:
            - Updates self.graph with detected relationships
            - Updates file metadata in graph (is_unparseable flag)
            - Logs warnings for skipped files or errors
        """
        # Stage 1: File Reading
        file_content = self._read_file(filepath)
        if file_content is None:
            # File was skipped (too large, encoding error, etc.)
            return False

        # Stage 2: AST Parsing
        try:
            module_ast = self._parse_ast(filepath, file_content)
            if module_ast is None:
                # Parsing failed (syntax error, timeout, etc.)
                self._mark_unparseable(filepath)
                return False
        except ASTParsingTimeoutError:
            logger.warning(
                f"⚠️ Skipping {filepath}: AST parsing exceeded timeout ({self.timeout_seconds}s)"
            )
            self._mark_unparseable(filepath)
            return False

        # Stage 3: Detector Dispatch
        relationships = self._dispatch_detectors(filepath, module_ast)

        # Stage 4: Relationship Storage
        self._store_relationships(filepath, relationships)

        return True

    def _read_file(self, filepath: str) -> Optional[str]:
        """Read file with UTF-8/latin-1 fallback and size limits.

        Implements file reading stage from TDD Section 3.5.1.

        Args:
            filepath: Absolute path to file to read.

        Returns:
            File contents as string, or None if file should be skipped.

        Error Recovery (EC-18):
        - File too large (EC-17): Skip, log warning, return None
        - Encoding errors: Try UTF-8 first, fallback to latin-1, log if non-UTF-8
        - File not found: Log error, return None
        - Permission errors: Log error, return None
        """
        try:
            # Check file exists and size limits (EC-17)
            path = Path(filepath)
            if not path.exists():
                logger.error(f"File not found: {filepath}")
                return None

            # Check file size in bytes to prevent memory exhaustion from files
            # with extremely long lines (security: memory exhaustion attack)
            file_size = path.stat().st_size
            if file_size > self.MAX_FILE_SIZE_BYTES:
                logger.warning(
                    f"⚠️ Skipping analysis of {filepath}: {file_size} bytes "
                    f"exceeds limit ({self.MAX_FILE_SIZE_BYTES})"
                )
                return None

            # Count lines before reading entire file
            with open(filepath, encoding="utf-8", errors="ignore") as f:
                line_count = sum(1 for _ in f)

            if line_count > self.max_file_lines:
                logger.warning(
                    f"⚠️ Skipping analysis of {filepath}: {line_count} lines "
                    f"exceeds limit ({self.max_file_lines})"
                )
                return None

            # Try UTF-8 encoding first
            try:
                with open(filepath, encoding="utf-8") as f:
                    return f.read()
            except UnicodeDecodeError:
                # Fallback to latin-1 (accepts all byte values)
                logger.warning(f"⚠️ File {filepath} is not UTF-8, using latin-1 fallback encoding")
                with open(filepath, encoding="latin-1") as f:
                    return f.read()

        except FileNotFoundError:
            logger.error(f"File not found: {filepath}")
            return None
        except PermissionError:
            logger.error(f"Permission denied reading file: {filepath}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading {filepath}: {e}")
            return None

    def _parse_ast(self, filepath: str, source: str) -> Optional[ast.Module]:
        """Parse source code into AST with timeout protection.

        Implements AST parsing stage from TDD Section 3.5.1.

        Uses concurrent.futures for cross-platform timeout support (works on
        both Unix and Windows).

        Args:
            filepath: Path to file being parsed (for error reporting).
            source: Source code to parse.

        Returns:
            AST Module node, or None if parsing failed.

        Raises:
            ASTParsingTimeoutError: If parsing exceeds timeout limit.

        Error Recovery (EC-18):
        - Syntax errors: Log warning with line number, return None
        - Timeout: Raise ASTParsingTimeoutError (caller handles)
        """

        def _do_parse() -> Optional[ast.Module]:
            """Internal function to perform the actual parsing."""
            try:
                return ast.parse(source, filename=filepath, mode="exec")
            except SyntaxError as e:
                logger.warning(f"⚠️ Skipping {filepath}: Syntax error at line {e.lineno}: {e.msg}")
                return None

        try:
            # Use ThreadPoolExecutor with timeout for cross-platform support
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_do_parse)
                try:
                    result = future.result(timeout=self.timeout_seconds)
                    return result
                except concurrent.futures.TimeoutError as e:
                    # Parsing exceeded timeout limit
                    raise ASTParsingTimeoutError(
                        f"AST parsing timeout ({self.timeout_seconds}s)"
                    ) from e
        except ASTParsingTimeoutError:
            # Re-raise timeout for caller to handle
            raise
        except Exception as e:
            # Unexpected parsing error
            logger.error(f"Unexpected error parsing {filepath}: {e}")
            return None

    def _dispatch_detectors(self, filepath: str, module_ast: ast.Module) -> List[Relationship]:
        """Dispatch AST nodes to registered detectors.

        Implements detector dispatch stage from TDD Section 3.5.1.

        This method traverses the AST and invokes all registered detectors
        for each node in priority order.

        Args:
            filepath: Path to file being analyzed.
            module_ast: Root AST node of the module.

        Returns:
            List of all detected relationships (aggregated from all detectors).

        Error Recovery:
        - Detector exceptions: Log error, continue with other detectors
        - Partial analysis: Return relationships from successful detectors
        """
        all_relationships: List[Relationship] = []
        detectors = self.detector_registry.get_detectors()

        # Traverse AST with depth limit
        def traverse_node(node: ast.AST, depth: int = 0) -> None:
            """Recursively traverse AST node and invoke detectors.

            Args:
                node: AST node to process.
                depth: Current recursion depth (for limit enforcement).
            """
            # Check recursion depth limit
            if depth > self.max_recursion_depth:
                logger.warning(
                    f"⚠️ AST traversal depth limit ({self.max_recursion_depth}) "
                    f"exceeded in {filepath}, skipping subtree"
                )
                return

            # Invoke all detectors for this node
            for detector in detectors:
                try:
                    relationships = detector.detect(node, filepath, module_ast)
                    all_relationships.extend(relationships)
                except Exception as e:
                    logger.error(f"Error in detector '{detector.name()}' for {filepath}: {e}")
                    # Continue with other detectors (partial analysis)

            # Recursively process child nodes
            for child in ast.iter_child_nodes(node):
                traverse_node(child, depth + 1)

        # Start traversal from root
        traverse_node(module_ast)

        return all_relationships

    def _store_relationships(self, filepath: str, relationships: List[Relationship]) -> None:
        """Store detected relationships in graph.

        Implements relationship storage stage from TDD Section 3.5.1.

        Args:
            filepath: Path to file that was analyzed.
            relationships: List of detected relationships to store.

        Side Effects:
            - Adds relationships to self.graph
            - Updates file metadata in graph (including dynamic pattern info)
            - Deduplicates relationships automatically (graph handles this)
        """
        # Remove old relationships for this file (incremental update)
        self.graph.remove_relationships_for_file(filepath)

        # Add new relationships
        for rel in relationships:
            self.graph.add_relationship(rel)

        # Aggregate dynamic pattern metadata from detectors (Section 3.5.4)
        dynamic_pattern_types = self._collect_dynamic_patterns()

        # Update file metadata
        metadata = FileMetadata(
            filepath=filepath,
            last_analyzed=time.time(),
            relationship_count=len(relationships),
            has_dynamic_patterns=len(dynamic_pattern_types) > 0,
            dynamic_pattern_types=dynamic_pattern_types,
            is_unparseable=False,
        )
        self.graph.set_file_metadata(filepath, metadata)

        # Note: Dynamic pattern warnings are NOT cleared here.
        # The service's _collect_detector_warnings() handles collecting and clearing.
        # This allows the service to aggregate warnings across analysis calls.

        if dynamic_pattern_types:
            logger.debug(
                f"Stored {len(relationships)} relationships for {filepath} "
                f"(dynamic patterns: {dynamic_pattern_types})"
            )
        else:
            logger.debug(f"Stored {len(relationships)} relationships for {filepath}")

    def _collect_dynamic_patterns(self) -> List[str]:
        """Collect detected dynamic pattern types from all detectors.

        Iterates through registered detectors, finds DynamicPatternDetector
        instances, and aggregates their detected pattern types.

        Returns:
            List of unique dynamic pattern type strings.
        """
        pattern_types: Set[str] = set()

        for detector in self.detector_registry.get_detectors():
            if isinstance(detector, DynamicPatternDetector):
                pattern_types.update(detector.get_pattern_types())

        return sorted(pattern_types)

    def _clear_dynamic_pattern_warnings(self) -> None:
        """Clear dynamic pattern warnings from all detectors.

        Called after storing relationships to reset detector state for next file.
        """
        for detector in self.detector_registry.get_detectors():
            if isinstance(detector, DynamicPatternDetector):
                detector.clear_warnings()

    def _mark_unparseable(self, filepath: str) -> None:
        """Mark a file as unparseable in graph metadata.

        Args:
            filepath: Path to file that failed parsing.
        """
        metadata = FileMetadata(
            filepath=filepath,
            last_analyzed=time.time(),
            relationship_count=0,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=True,  # EC-18: Mark as unparseable
        )
        self.graph.set_file_metadata(filepath, metadata)

    # =========================================================================
    # Two-Phase Analysis Methods (Issue #122)
    # =========================================================================

    def extract_file_symbols(self, filepath: str) -> Optional[FileSymbolData]:
        """Extract FileSymbolData from a Python file (Issue #122 Phase 1).

        This method implements the first phase of the two-phase analysis approach:
        AST -> FileSymbolData

        Uses detectors that support symbol extraction mode to extract all
        definitions and references from a file without creating relationships.

        Args:
            filepath: Absolute path to Python file to analyze.

        Returns:
            FileSymbolData containing all symbols, or None if file couldn't be parsed.
        """
        # Stage 1: File Reading
        file_content = self._read_file(filepath)
        if file_content is None:
            return None

        # Stage 2: AST Parsing
        try:
            module_ast = self._parse_ast(filepath, file_content)
            if module_ast is None:
                return FileSymbolData(
                    filepath=filepath,
                    definitions=[],
                    references=[],
                    parse_time=time.time(),
                    is_valid=False,
                    error_message="Syntax error in file",
                )
        except ASTParsingTimeoutError:
            logger.warning(f"⚠️ Symbol extraction timeout for {filepath} ({self.timeout_seconds}s)")
            return FileSymbolData(
                filepath=filepath,
                definitions=[],
                references=[],
                parse_time=time.time(),
                is_valid=False,
                error_message=f"AST parsing timeout ({self.timeout_seconds}s)",
            )

        # Stage 3: Symbol Extraction
        definitions, references = self._extract_symbols(filepath, module_ast)

        # Collect dynamic pattern info
        dynamic_pattern_types = self._collect_dynamic_patterns()

        return FileSymbolData(
            filepath=filepath,
            definitions=definitions,
            references=references,
            parse_time=time.time(),
            is_valid=True,
            has_dynamic_patterns=len(dynamic_pattern_types) > 0,
            dynamic_pattern_types=dynamic_pattern_types if dynamic_pattern_types else None,
        )

    def _extract_symbols(
        self, filepath: str, module_ast: ast.Module
    ) -> Tuple[List[SymbolDefinition], List[SymbolReference]]:
        """Extract symbols from AST using detectors that support symbol extraction.

        Args:
            filepath: Path to file being analyzed.
            module_ast: Root AST node of the module.

        Returns:
            Tuple of (definitions, references) aggregated from all symbol-enabled detectors.
        """
        all_definitions: List[SymbolDefinition] = []
        all_references: List[SymbolReference] = []
        detectors = self.detector_registry.get_detectors()

        # Filter to detectors that support symbol extraction
        symbol_detectors = [d for d in detectors if d.supports_symbol_extraction()]

        def traverse_node(node: ast.AST, depth: int = 0) -> None:
            """Recursively traverse AST and extract symbols."""
            if depth > self.max_recursion_depth:
                logger.warning(
                    f"⚠️ AST traversal depth limit ({self.max_recursion_depth}) "
                    f"exceeded in {filepath}, skipping subtree"
                )
                return

            # Invoke symbol extraction on all enabled detectors
            for detector in symbol_detectors:
                try:
                    definitions, references = detector.extract_symbols(node, filepath, module_ast)
                    all_definitions.extend(definitions)
                    all_references.extend(references)
                except Exception as e:
                    logger.error(
                        f"Error in detector '{detector.name()}' symbol extraction "
                        f"for {filepath}: {e}"
                    )

            # Recursively process child nodes
            for child in ast.iter_child_nodes(node):
                traverse_node(child, depth + 1)

        traverse_node(module_ast)

        return (all_definitions, all_references)

    def analyze_file_two_phase(
        self,
        filepath: str,
        symbol_data: Optional[FileSymbolData] = None,
        relationship_builder: Optional[RelationshipBuilder] = None,
    ) -> bool:
        """Analyze a file using the two-phase approach (Issue #122, #125).

        This method implements the full two-phase analysis:
        Phase 1: AST -> FileSymbolData (via extract_file_symbols)
        Phase 2: FileSymbolData -> Relationships (via RelationshipBuilder)

        This approach enables:
        - Incremental analysis (reuse symbol data for unchanged files)
        - Better cross-file resolution (RelationshipBuilder can resolve across files)
        - Symbol data inspection independent of relationship creation

        Args:
            filepath: Absolute path to Python file to analyze.
            symbol_data: Optional pre-extracted FileSymbolData. If None, extracts symbols first.
            relationship_builder: Optional RelationshipBuilder to use for cross-file resolution.
                                  If None, creates a single-file builder (less accurate).

        Returns:
            True if analysis succeeded, False if file was skipped or failed.
        """
        # Phase 1: Get or extract FileSymbolData
        if symbol_data is None:
            symbol_data = self.extract_file_symbols(filepath)

        if symbol_data is None:
            return False

        if not symbol_data.is_valid:
            self._mark_unparseable(filepath)
            return False

        # Phase 2: Build relationships from symbol data using RelationshipBuilder
        if relationship_builder is None:
            # Create a single-file builder for this file only
            relationship_builder = RelationshipBuilder()

        # Add or update this file's symbol data in the builder
        relationship_builder.remove_file_data(filepath)  # Remove old data if exists
        relationship_builder.add_file_data(symbol_data)

        # Build relationships for this file
        relationships = relationship_builder.build_relationships_for_file(filepath)

        # Store relationships in graph
        self._store_relationships(filepath, relationships)

        return True

    def analyze_project_two_phase(
        self,
        filepaths: List[str],
        relationship_builder: Optional[RelationshipBuilder] = None,
    ) -> Tuple[int, int, RelationshipBuilder]:
        """Analyze multiple files using two-phase approach with shared builder.

        This method provides the full benefit of two-phase analysis by:
        1. Extracting symbol data from all files first (Phase 1)
        2. Building relationships with cross-file resolution (Phase 2)

        Args:
            filepaths: List of absolute paths to Python files to analyze.
            relationship_builder: Optional RelationshipBuilder. If None, creates new one.

        Returns:
            Tuple of (success_count, failed_count, relationship_builder).
            The relationship_builder can be reused for incremental updates.
        """
        if relationship_builder is None:
            relationship_builder = RelationshipBuilder()

        success_count = 0
        failed_count = 0

        # Phase 1: Extract symbol data from all files
        symbol_data_map: dict[str, FileSymbolData] = {}
        for filepath in filepaths:
            symbol_data = self.extract_file_symbols(filepath)
            if symbol_data is not None and symbol_data.is_valid:
                symbol_data_map[filepath] = symbol_data
                relationship_builder.remove_file_data(filepath)
                relationship_builder.add_file_data(symbol_data)
            elif symbol_data is not None and not symbol_data.is_valid:
                self._mark_unparseable(filepath)
                failed_count += 1
            else:
                failed_count += 1

        # Phase 2: Build relationships for all files with cross-file resolution
        for filepath in symbol_data_map:
            relationships = relationship_builder.build_relationships_for_file(filepath)
            self._store_relationships(filepath, relationships)
            success_count += 1

        return (success_count, failed_count, relationship_builder)
