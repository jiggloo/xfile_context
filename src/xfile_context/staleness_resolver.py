# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Staleness resolver for transitive dependency tracking (Issue #117 Option B).

This module implements the topological sort-based algorithm for resolving stale
files and their transitive dependencies when read_with_context() is called.

Algorithm Overview:
1. Copy dependency graph before modifications
2. Find stale files in transitive dependency chain
3. Sort topologically (dependencies before dependents)
4. Remove relationships and mark dependents as pending
5. Analyze stale files in topological order
6. Rebuild relationships for pending files from symbol data (Issue #133 fix)

This approach ensures correct handling of complex dependency chains including:
- Diamond patterns (A -> B, A -> C, B -> D, C -> D)
- Transitive staleness (A -> B -> C, where C is stale)
- Partial staleness (A -> B -> C, where A and C are stale but not B)

Issue #133 Fix:
When analyze_file() is called for a stale file, it calls remove_relationships_for_file()
which removes ALL relationships involving the file, including incoming relationships
from dependents. Instead of storing/restoring relationships (which is brittle), we
rebuild them from the symbol data in the RelationshipBuilder. This is cleaner because
relationships are derived from the authoritative source (FileSymbolData).

See Issue #117 comments for detailed algorithm discussion.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Set

from xfile_context.models import RelationshipGraph

if TYPE_CHECKING:
    from xfile_context.relationship_builder import RelationshipBuilder

logger = logging.getLogger(__name__)


class StalenessResolver:
    """Resolves stale files using topological sort-based traversal.

    Implements Issue #117 Option B: Full transitive dependency check with
    efficient pending relationship handling.

    Key Design Decisions:
    - Uses topological sort to ensure dependencies are processed before dependents
    - Rebuilds relationships from symbol data for pending files (Issue #133 fix)
    - Marks files as "pending relationships" to avoid unnecessary re-analysis
    - Works with copied dependency graph to preserve traversal information

    Issue #133 Fix:
    When a stale file B is re-analyzed, analyze_file() calls remove_relationships_for_file(B)
    which removes ALL relationships involving B, including A -> B where A is a dependent.
    Instead of storing/restoring relationships (brittle), we rebuild A's relationships
    from A's FileSymbolData in the RelationshipBuilder. This works because:
    1. FileSymbolData is the authoritative source for relationships
    2. RelationshipBuilder.build_relationships_for_file() can rebuild any file's relationships
    3. This approach is simpler and handles all edge cases automatically

    Usage:
        resolver = StalenessResolver(graph, needs_analysis_fn, analyze_fn, relationship_builder)
        resolver.resolve_staleness(target_file)
    """

    def __init__(
        self,
        graph: RelationshipGraph,
        needs_analysis: Callable[[str], bool],
        analyze_file: Callable[[str], bool],
        relationship_builder: Optional["RelationshipBuilder"] = None,
    ):
        """Initialize the staleness resolver.

        Args:
            graph: RelationshipGraph to operate on.
            needs_analysis: Function that returns True if file needs re-analysis.
                           Signature: (filepath: str) -> bool
            analyze_file: Function to analyze a file and update the graph.
                         Signature: (filepath: str) -> bool (success)
            relationship_builder: Optional RelationshipBuilder for rebuilding
                                  relationships from symbol data. Required for
                                  the Issue #133 fix to work correctly.
        """
        self.graph = graph
        self.needs_analysis = needs_analysis
        self.analyze_file = analyze_file
        self._relationship_builder = relationship_builder

        # Track pending files that need relationship rebuilding
        self._pending_files: Set[str] = set()

    def resolve_staleness(self, target_file: str) -> bool:
        """Resolve staleness for target file and its transitive dependencies.

        Implements the Option B algorithm:
        1. Copy dependency graph before modifications
        2. Find stale files in transitive dependency chain
        3. Sort topologically (dependencies before dependents)
        4. Remove relationships and mark dependents as pending
        5. Analyze/restore files in topological order

        Example Scenarios:
        - Diamond pattern: A -> B, A -> C, B -> D, C -> D
          If D is stale, D is processed first, then B and C, then A.
        - Transitive staleness: A -> B -> C
          If C is stale, C is processed before B, then B before A.
        - Partial staleness: A -> B -> C where A and C are stale but not B
          C is processed first, then A. B's relationships are restored.

        Args:
            target_file: File being read via read_with_context().

        Returns:
            True if resolution succeeded, False if any file analysis failed.
            Note: Processing continues even if some files fail; the return
            value indicates if ALL files were processed successfully.
        """
        logger.debug(f"Starting staleness resolution for {target_file}")

        # Step 1: Copy dependency graph before any modifications
        dependency_graph_copy = self.graph.copy_dependency_graph()

        # Step 2: Find all stale files in the transitive dependency chain
        stale_files = self._find_stale_files(target_file, dependency_graph_copy)

        if not stale_files:
            logger.debug(f"No stale files found in dependency chain of {target_file}")
            return True

        logger.debug(f"Found {len(stale_files)} stale files: {stale_files}")

        # Step 3: Topologically sort stale files (dependencies first)
        sorted_stale_files = self._topological_sort_stale_files(stale_files, dependency_graph_copy)

        logger.debug(f"Topological order for stale files: {sorted_stale_files}")

        # Step 4: Remove relationships and mark dependents as pending
        self._remove_relationships_and_mark_pending(sorted_stale_files)

        # Step 5: Generate updated topological order including pending files
        files_to_process = self._get_files_to_process(
            target_file, stale_files, dependency_graph_copy
        )

        logger.debug(f"Files to process in order: {files_to_process}")

        # Step 6: Analyze/restore files in topological order
        return self._process_files(files_to_process, stale_files)

    def _find_stale_files(
        self, target_file: str, dependency_graph: Dict[str, Set[str]]
    ) -> Set[str]:
        """Find all stale files in the transitive dependency chain.

        Checks the target file and all its transitive dependencies for staleness.
        A file is stale if needs_analysis() returns True.

        Args:
            target_file: Starting file to check.
            dependency_graph: Copied dependency graph for traversal.

        Returns:
            Set of filepaths that are stale (need re-analysis).
        """
        stale_files: Set[str] = set()

        # Check target file
        if self.needs_analysis(target_file):
            stale_files.add(target_file)

        # Get all transitive dependencies
        transitive_deps = self.graph.get_transitive_dependencies(target_file, dependency_graph)

        # Check each dependency for staleness
        # Skip special marker paths like <stdlib:os>, <third-party:requests>
        # These represent external dependencies that cannot be analyzed
        for dep in transitive_deps:
            if dep.startswith("<") and dep.endswith(">"):
                continue

            if self.needs_analysis(dep):
                stale_files.add(dep)

        return stale_files

    def _topological_sort_stale_files(
        self, stale_files: Set[str], dependency_graph: Dict[str, Set[str]]
    ) -> List[str]:
        """Sort stale files topologically (dependencies before dependents).

        Uses Kahn's algorithm to sort files such that if A depends on B,
        B comes before A in the result. This ensures dependencies are
        analyzed before files that depend on them.

        The sort considers transitive reachability: if A -> B -> C (even if B
        is not stale), and both A and C are stale, C should come before A.

        Args:
            stale_files: Set of stale file paths.
            dependency_graph: Copied dependency graph for traversal.

        Returns:
            List of stale files in topological order (dependencies first).
        """
        if not stale_files:
            return []

        # Build dependency graph restricted to stale files (with transitive edges)
        # A stale file A transitively depends on stale file B if there's any path A -> ... -> B
        stale_deps: Dict[str, Set[str]] = {f: set() for f in stale_files}

        for stale_file in stale_files:
            # Find which other stale files this one transitively depends on
            all_deps = self.graph.get_transitive_dependencies(stale_file, dependency_graph)
            for dep in all_deps:
                if dep in stale_files:
                    stale_deps[stale_file].add(dep)

        # Kahn's algorithm for topological sort:
        # 1. Calculate in-degree for each node (number of stale dependencies it has)
        # 2. Start with nodes that have no stale dependencies (in-degree = 0)
        # 3. Process each node, decrementing in-degree of files that depend on it
        # 4. Add nodes with in-degree = 0 to queue
        # 5. Repeat until all nodes processed
        #
        # Example: For A -> B -> C (all stale), returns [C, B, A]
        # because C has no stale deps, B depends on C, A depends on B.
        #
        # Performance note: O(N² × E) worst case where N = stale files, E = edges.
        # For v0.1.0 target scale (10K files), this is acceptable (~100-500ms worst case).
        in_degree: Dict[str, int] = {f: len(stale_deps[f]) for f in stale_files}

        # Start with files that have no stale dependencies (they can be processed first)
        queue: List[str] = [f for f in stale_files if in_degree[f] == 0]
        result: List[str] = []

        while queue:
            # Sort queue for deterministic ordering (helps with testing/debugging)
            queue.sort()
            current = queue.pop(0)
            result.append(current)

            # Decrement in-degree for files that depend on current
            for stale_file in stale_files:
                if current in stale_deps[stale_file]:
                    in_degree[stale_file] -= 1
                    if in_degree[stale_file] == 0 and stale_file not in result:
                        queue.append(stale_file)

        # Handle cycles (shouldn't happen in well-formed graphs)
        if len(result) != len(stale_files):
            remaining = [f for f in stale_files if f not in result]
            logger.warning(f"Cycle detected in stale files, adding remaining: {remaining}")
            result.extend(sorted(remaining))

        return result

    def _remove_relationships_and_mark_pending(self, sorted_stale_files: List[str]) -> None:
        """Remove relationships for stale files and mark dependents as pending.

        For each stale file in topological order:
        1. Remove its outgoing relationships from the graph
        2. Mark all direct dependents as pending_relationships
        3. Track pending files for later relationship rebuilding (Issue #133 fix)

        Issue #133 Note:
        We don't store relationships anymore. When analyze_file() is called for a stale
        file, it removes ALL relationships including incoming ones from dependents.
        Instead of storing/restoring, we'll rebuild relationships from symbol data.

        Args:
            sorted_stale_files: Stale files in topological order.
        """
        for filepath in sorted_stale_files:
            # Remove outgoing relationships
            removed = self.graph.remove_outgoing_relationships(filepath)

            # Mark direct dependents as pending and track them for rebuilding
            # Issue #133: These dependents will have their A -> B relationships
            # removed when analyze_file(B) is called. We'll rebuild them later
            # from their FileSymbolData in the RelationshipBuilder.
            dependents = self.graph.get_direct_dependents(filepath)
            for dependent in dependents:
                # Skip special markers
                if dependent.startswith("<") and dependent.endswith(">"):
                    continue
                self.graph.mark_file_pending_relationships(dependent)
                self._pending_files.add(dependent)

            logger.debug(
                f"Removed {len(removed)} relationships from {Path(filepath).name}, "
                f"marked {len(dependents)} dependents as pending"
            )

    def _get_files_to_process(
        self,
        target_file: str,
        stale_files: Set[str],
        dependency_graph: Dict[str, Set[str]],
    ) -> List[str]:
        """Get files to process in order (stale + pending files).

        Creates a topological ordering of all files that need processing:
        - Stale files (need re-analysis)
        - Files marked as pending_relationships (need relationship restoration)

        Files are ordered such that dependencies come before dependents.

        Args:
            target_file: The original target file.
            stale_files: Set of stale file paths.
            dependency_graph: Original (copied) dependency graph.

        Returns:
            List of filepaths to process in order.
        """
        # Get all pending files
        pending_files = set(self.graph.get_files_with_pending_relationships())

        # Also mark stale files as pending (they need processing too)
        all_files_to_process = stale_files | pending_files

        # Filter to files reachable from target_file in original graph
        reachable = self.graph.get_transitive_dependencies(target_file, dependency_graph)
        reachable.add(target_file)

        files_to_process = all_files_to_process & reachable

        # Topologically sort all files to process
        return self._topological_sort_files(files_to_process, dependency_graph)

    def _topological_sort_files(
        self, files: Set[str], dependency_graph: Dict[str, Set[str]]
    ) -> List[str]:
        """Topologically sort a set of files based on dependency graph.

        Args:
            files: Set of files to sort.
            dependency_graph: Dependency graph for ordering.

        Returns:
            Topologically sorted list (dependencies first).
        """
        if not files:
            return []

        # Build restricted dependency graph
        deps: Dict[str, Set[str]] = {f: set() for f in files}
        for filepath in files:
            all_deps = self.graph.get_transitive_dependencies(filepath, dependency_graph)
            for dep in all_deps:
                if dep in files:
                    deps[filepath].add(dep)

        # Kahn's algorithm
        # in_degree[f] = number of dependencies f depends on (must process first)
        in_degree: Dict[str, int] = {f: len(deps[f]) for f in files}

        queue: List[str] = [f for f in files if in_degree[f] == 0]
        result: List[str] = []

        while queue:
            queue.sort()
            current = queue.pop(0)
            result.append(current)

            # For each file that depends on current
            for filepath in files:
                if current in deps[filepath]:
                    in_degree[filepath] -= 1
                    if in_degree[filepath] == 0 and filepath not in result:
                        queue.append(filepath)

        # Handle any remaining files (cycles)
        if len(result) != len(files):
            remaining = [f for f in files if f not in result]
            result.extend(sorted(remaining))

        return result

    def _process_files(self, files_to_process: List[str], stale_files: Set[str]) -> bool:
        """Process files in topological order (analyze or rebuild relationships).

        For each file:
        - If stale: Re-analyze the file via analyze_file callback
        - If pending (not stale): Rebuild relationships from symbol data (Issue #133 fix)

        Issue #133 Fix:
        When a stale file B is analyzed, remove_relationships_for_file(B) removes
        ALL relationships involving B, including A -> B where A is a dependent.
        Instead of restoring from stored relationships (brittle), we rebuild A's
        relationships from A's FileSymbolData using the RelationshipBuilder.

        Processing continues even if individual files fail, ensuring maximum
        recovery. Failed files are logged but don't stop subsequent processing.

        Args:
            files_to_process: Files in topological order (dependencies first).
            stale_files: Set of files that need re-analysis.

        Returns:
            True if ALL files processed successfully, False if ANY failed.
            Note: Even on False return, all files were attempted.
        """
        success = True

        for filepath in files_to_process:
            if filepath in stale_files:
                # Re-analyze the file
                logger.debug(f"Re-analyzing stale file: {Path(filepath).name}")
                if not self.analyze_file(filepath):
                    logger.warning(f"Failed to analyze stale file: {filepath}")
                    success = False
            else:
                # Rebuild relationships for pending file from symbol data (Issue #133 fix)
                logger.debug(f"Rebuilding relationships for pending file: {Path(filepath).name}")
                self._rebuild_relationships_for_file(filepath)

            # Clear pending flag
            self.graph.clear_pending_relationships(filepath)

        # Clear pending files tracking
        self._pending_files.clear()

        return success

    def _rebuild_relationships_for_file(self, filepath: str) -> None:
        """Rebuild relationships for a file from its symbol data (Issue #133 fix).

        This method rebuilds a file's outgoing relationships by:
        1. Looking up the file's FileSymbolData in the RelationshipBuilder
        2. Using RelationshipBuilder.build_relationships_for_file() to derive relationships
        3. Replacing the file's relationships in the graph

        This is called for pending files (dependents of stale files) whose relationships
        were removed when the stale file was analyzed.

        Args:
            filepath: Path to file needing relationship rebuild.
        """
        if self._relationship_builder is None:
            # Fallback: No relationship builder available, can't rebuild
            # This shouldn't happen in normal operation as two-phase analysis
            # should always be enabled per the Issue #133 fix requirements
            logger.warning(
                f"Cannot rebuild relationships for {Path(filepath).name}: "
                "RelationshipBuilder not available"
            )
            return

        # Check if we have symbol data for this file
        file_data = self._relationship_builder.get_file_data(filepath)
        if file_data is None:
            logger.debug(
                f"No symbol data for {Path(filepath).name}, " "skipping relationship rebuild"
            )
            return

        # Rebuild relationships from symbol data
        relationships = self._relationship_builder.build_relationships_for_file(filepath)

        # Remove any existing relationships for this file and add the rebuilt ones
        # Note: We only remove outgoing relationships to preserve incoming ones
        # that may have been added by other files' analysis
        self.graph.remove_outgoing_relationships(filepath)
        for rel in relationships:
            self.graph.add_relationship(rel)

        logger.debug(f"Rebuilt {len(relationships)} relationships for {Path(filepath).name}")
