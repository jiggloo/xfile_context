# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Staleness resolution for transitive dependencies (Issue #117 Option B).

This module implements the topological sort-based algorithm for resolving
stale files and their transitive dependencies when read_with_context() is called.

Algorithm Overview:
1. Copy the dependency graph before any modifications
2. Remove relationships by topological order (dependencies first)
3. Mark dependent files as pending relationships
4. Generate topological sorted list of pending files
5. Analyze/restore files in topological order

See Issue #117 for detailed algorithm specification.
"""

import logging
from typing import Callable, Dict, List, Set

from xfile_context.models import FileMetadata, RelationshipGraph

logger = logging.getLogger(__name__)


class StalenessResolver:
    """Resolves stale files and transitive dependencies.

    This class implements the Option B algorithm from Issue #117:
    - Topological sort of stale transitive dependencies
    - Efficient relationship storage/restoration for non-stale files
    - Correct ordering to avoid missing relationships
    """

    def __init__(
        self,
        graph: RelationshipGraph,
        is_file_stale: Callable[[str], bool],
        analyze_file: Callable[[str], bool],
    ):
        """Initialize the staleness resolver.

        Args:
            graph: The relationship graph to operate on.
            is_file_stale: Function that returns True if file needs re-analysis
                (content changed since last analysis).
            analyze_file: Function to analyze a file and update the graph.
        """
        self._graph = graph
        self._is_file_stale = is_file_stale
        self._analyze_file = analyze_file

    def resolve_staleness(self, target_file: str) -> List[str]:
        """Resolve staleness for a target file and its transitive dependencies.

        Implements the Option B algorithm from Issue #117:
        1. Copy the dependency graph
        2. Find all stale files in transitive dependency chain
        3. Topologically sort stale files (dependencies before dependents)
        4. Remove relationships and mark dependents as pending
        5. Analyze/restore files in topological order

        Args:
            target_file: The file being read via read_with_context().

        Returns:
            List of files that were analyzed or had relationships restored.
        """
        # Step 1: Copy the dependency graph before any modifications
        original_graph = self._graph.copy_dependency_graph()

        # Find all transitive dependencies from the target file
        all_deps = self._graph.get_transitive_dependencies(target_file, original_graph)

        # Include target file itself
        files_to_check = [target_file] + all_deps

        # Find which files are stale (content changed)
        stale_files = [f for f in files_to_check if self._is_file_stale(f)]

        if not stale_files:
            logger.debug(f"No stale files found for {target_file}")
            return []

        logger.debug(f"Found {len(stale_files)} stale files: {stale_files}")

        # Step 2-3: Topologically sort stale files (dependencies first)
        sorted_stale = self._topological_sort(stale_files, original_graph)
        logger.debug(f"Topological order of stale files: {sorted_stale}")

        # Track files that need relationship restoration
        pending_files: Set[str] = set()

        # Step 2: Remove relationships by topological order
        for filepath in sorted_stale:
            # Store relationships before removing (for dependents that aren't stale)
            self._store_and_mark_dependents(filepath, pending_files)

            # Remove relationships for this file
            self._graph.remove_relationships_for_file(filepath)

        # Mark stale files as pending too (they need new relationships added)
        pending_files.update(stale_files)

        # Step 4: Generate updated topological sorted list of pending files
        # that are in the dependency chain of the target file
        pending_in_chain = [
            f for f in self._get_pending_in_chain(target_file, original_graph) if f in pending_files
        ]
        sorted_pending = self._topological_sort(pending_in_chain, original_graph)
        logger.debug(f"Topological order of pending files: {sorted_pending}")

        # Step 5: Analyze or restore files in topological order
        processed: List[str] = []
        for filepath in sorted_pending:
            if filepath in stale_files:
                # Stale file: needs full re-analysis
                logger.debug(f"Re-analyzing stale file: {filepath}")
                self._analyze_file(filepath)
                # Clear pending flag after analysis
                self._clear_pending_flag(filepath)
            else:
                # Not stale, just pending: restore relationships
                logger.debug(f"Restoring relationships for pending file: {filepath}")
                if self._graph.restore_pending_relationships(filepath):
                    self._clear_pending_flag(filepath)

            processed.append(filepath)

        return processed

    def _topological_sort(
        self,
        files: List[str],
        dependency_graph: Dict[str, Set[str]],
    ) -> List[str]:
        """Topologically sort files so dependencies come before dependents.

        Uses Kahn's algorithm for topological sorting, but considers transitive
        dependencies. If file A can reach file C through any path (even through
        files not in the sort set), C should come before A.

        Args:
            files: List of files to sort.
            dependency_graph: The dependency graph to use for ordering.

        Returns:
            Files sorted in topological order (dependencies first).
        """
        if not files:
            return []

        file_set = set(files)

        # Build transitive reachability: for each file, which files in the set
        # can it transitively reach?
        def get_reachable_in_set(start: str) -> Set[str]:
            """Get all files in file_set that are transitively reachable from start."""
            visited: Set[str] = set()
            reachable: Set[str] = set()

            def visit(path: str) -> None:
                if path in visited:
                    return
                visited.add(path)

                if path in file_set and path != start:
                    reachable.add(path)

                for dep in dependency_graph.get(path, set()):
                    # Skip special markers
                    if dep.startswith("<") and dep.endswith(">"):
                        continue
                    visit(dep)

            # Start from the file's direct dependencies
            for dep in dependency_graph.get(start, set()):
                if dep.startswith("<") and dep.endswith(">"):
                    continue
                visit(dep)

            return reachable

        # Build in-degree map using transitive reachability
        in_degree: Dict[str, int] = {f: 0 for f in files}
        reachability: Dict[str, Set[str]] = {}

        for filepath in files:
            reachable = get_reachable_in_set(filepath)
            reachability[filepath] = reachable
            in_degree[filepath] = len(reachable)

        # Start with files that have no transitive dependencies in the set
        queue: List[str] = [f for f in files if in_degree[f] == 0]
        result: List[str] = []

        while queue:
            filepath = queue.pop(0)
            result.append(filepath)

            # For each file that can reach this one, decrement in-degree
            for other in files:
                if other == filepath:
                    continue
                if filepath in reachability.get(other, set()):
                    in_degree[other] -= 1
                    if in_degree[other] == 0:
                        queue.append(other)

        # If we didn't process all files, there's a cycle - just append remaining
        if len(result) < len(files):
            remaining = [f for f in files if f not in result]
            logger.warning(f"Cycle detected in dependencies, appending remaining: {remaining}")
            result.extend(remaining)

        return result

    def _store_and_mark_dependents(
        self,
        filepath: str,
        pending_files: Set[str],
    ) -> None:
        """Store relationships for dependents and mark them as pending.

        When we remove relationships for a file, its dependents lose their
        relationships TO this file. We need to mark those dependents as
        pending so their relationships can be restored later.

        Args:
            filepath: File whose relationships are being removed.
            pending_files: Set to add pending file paths to.
        """
        # Get files that depend on this file (have relationships pointing to it)
        dependents = self._graph.get_dependents(filepath)

        for rel in dependents:
            dependent_file = rel.source_file

            # Skip if already marked pending or if it's the file being removed
            if dependent_file in pending_files:
                continue

            # Store the dependent's relationships so they can be restored
            self._graph.store_pending_relationships(dependent_file)

            # Mark the dependent as pending in metadata
            self._set_pending_flag(dependent_file)

            pending_files.add(dependent_file)

    def _get_pending_in_chain(
        self,
        target_file: str,
        dependency_graph: Dict[str, Set[str]],
    ) -> List[str]:
        """Get all files in the dependency chain from target that need processing.

        Args:
            target_file: The target file being read.
            dependency_graph: The original dependency graph.

        Returns:
            List of files in the dependency chain (including target).
        """
        result = [target_file]
        result.extend(self._graph.get_transitive_dependencies(target_file, dependency_graph))
        return result

    def _set_pending_flag(self, filepath: str) -> None:
        """Set the pending_relationships flag for a file."""
        metadata = self._graph.get_file_metadata(filepath)
        if metadata:
            new_metadata = FileMetadata(
                filepath=metadata.filepath,
                last_analyzed=metadata.last_analyzed,
                relationship_count=metadata.relationship_count,
                has_dynamic_patterns=metadata.has_dynamic_patterns,
                dynamic_pattern_types=metadata.dynamic_pattern_types,
                is_unparseable=metadata.is_unparseable,
                deleted=metadata.deleted,
                deletion_time=metadata.deletion_time,
                pending_relationships=True,
            )
            self._graph.set_file_metadata(filepath, new_metadata)

    def _clear_pending_flag(self, filepath: str) -> None:
        """Clear the pending_relationships flag for a file."""
        metadata = self._graph.get_file_metadata(filepath)
        if metadata and metadata.pending_relationships:
            new_metadata = FileMetadata(
                filepath=metadata.filepath,
                last_analyzed=metadata.last_analyzed,
                relationship_count=metadata.relationship_count,
                has_dynamic_patterns=metadata.has_dynamic_patterns,
                dynamic_pattern_types=metadata.dynamic_pattern_types,
                is_unparseable=metadata.is_unparseable,
                deleted=metadata.deleted,
                deletion_time=metadata.deletion_time,
                pending_relationships=False,
            )
            self._graph.set_file_metadata(filepath, new_metadata)
