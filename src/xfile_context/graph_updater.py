# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Incremental graph updater for file system changes.

This module implements incremental update logic (TDD Section 3.6.3):
- On modify: Remove old relationships, re-analyze, add new relationships
- On delete: Remove all relationships, mark as deleted (EC-14)
- On create: Analyze and add to graph
- Atomic updates: No partial state visible
- Performance: <200ms target per file (NFR-1)

Design:
- Coordinates FileWatcher, PythonAnalyzer, and RelationshipGraph
- Ensures atomic updates through explicit rollback on failure
- Single-threaded operation (no concurrent modifications)

See TDD Section 3.6.3 for detailed specifications.
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from xfile_context.analyzers.python_analyzer import PythonAnalyzer
from xfile_context.file_watcher import FileWatcher
from xfile_context.models import FileMetadata, Relationship, RelationshipGraph
from xfile_context.relationship_builder import RelationshipBuilder

logger = logging.getLogger(__name__)


class GraphUpdater:
    """Coordinates incremental updates to relationship graph.

    This class implements the incremental update strategy from TDD Section 3.6.3:
    - File modification: Re-analyze only the modified file
    - File deletion: Remove relationships and mark as deleted (EC-14)
    - File creation: Analyze new file and add to graph

    Atomicity Guarantee:
    - Updates complete fully or not at all (except unparseable files - see below)
    - On failure: Rollback changes, log error, graph remains consistent
    - No partial state visible to graph queries
    - Exception: When file becomes unparseable, old relationships are removed
      as they are stale - this is the only case where rollback doesn't restore
      original state

    Performance:
    - Target: <200ms per file update (NFR-1)
    - Only modified file is re-analyzed, not entire codebase
    - Efficient index updates in RelationshipGraph

    Thread Safety:
    - NOT thread-safe: Designed for single-threaded use
    - Concurrent updates will cause race conditions

    See TDD Section 3.6.3 for detailed specifications.
    """

    def __init__(
        self,
        graph: RelationshipGraph,
        analyzer: PythonAnalyzer,
        file_watcher: FileWatcher,
        relationship_builder: Optional[RelationshipBuilder] = None,
    ):
        """Initialize graph updater.

        Args:
            graph: RelationshipGraph to update.
            analyzer: PythonAnalyzer for re-analyzing modified files.
            file_watcher: FileWatcher for detecting file changes.
            relationship_builder: RelationshipBuilder for two-phase analysis.
                Required for Issue #133 fix (symbol-based relationship rebuilding).
        """
        self.graph = graph
        self.analyzer = analyzer
        self.file_watcher = file_watcher
        self.relationship_builder = relationship_builder
        self.project_root = Path(file_watcher.project_root).resolve()

    def _validate_filepath(self, filepath: str) -> bool:
        """Validate that filepath is within project root (security check).

        Prevents path traversal attacks by ensuring all file operations
        stay within the monitored project directory.

        Args:
            filepath: Path to validate.

        Returns:
            True if filepath is within project_root, False otherwise.
        """
        try:
            path = Path(filepath).resolve()
            # Check if path is within project_root
            # Use try/except on relative_to for path normalization
            try:
                path.relative_to(self.project_root)
                return True
            except ValueError:
                # path is not relative to project_root
                return False
        except (OSError, ValueError) as e:
            logger.error(f"Invalid filepath during validation: {filepath}: {e}")
            return False

    def update_on_modify(self, filepath: str) -> bool:
        """Update graph when file is modified.

        Implements modification update from TDD Section 3.6.3:
        1. Remove old relationships from graph
        2. Re-analyze modified file
        3. Add new relationships to graph
        4. Update bidirectional indexes

        Atomicity: Uses snapshot-restore pattern for rollback on failure.

        Args:
            filepath: Absolute path to modified file.

        Returns:
            True if update succeeded, False if update failed.

        Performance Target:
            <200ms per file (NFR-1)
        """
        start_time = time.time()

        # Security: Validate filepath is within project root
        if not self._validate_filepath(filepath):
            logger.warning(f"Rejecting update for file outside project root: {filepath}")
            return False

        try:
            logger.debug(f"Updating graph for modified file: {filepath}")

            # Stage 1: Snapshot current state for potential rollback
            old_relationships = self.graph.get_dependencies(filepath) + self.graph.get_dependents(
                filepath
            )
            old_metadata = self.graph.get_file_metadata(filepath)

            # Stage 2: Remove old relationships
            # Note: PythonAnalyzer.analyze_file_two_phase() calls _store_relationships()
            # which already removes old relationships before adding new ones
            # So we just need to call analyze_file_two_phase()

            # Stage 3: Re-analyze file using two-phase analysis
            # (this also removes old relationships)
            # Two-phase analysis is always enabled (Issue #133 fix requirement)
            success = self.analyzer.analyze_file_two_phase(
                filepath, relationship_builder=self.relationship_builder
            )

            if not success:
                # Analysis failed (syntax error, timeout, etc.)
                # File is already marked as unparseable by analyzer
                logger.warning(f"Re-analysis failed for {filepath}, file marked as unparseable")
                # Note: Old relationships are already removed by analyze_file()
                # This is acceptable - file is unparseable so relationships are stale

            elapsed = time.time() - start_time
            logger.debug(f"Graph update for {filepath} completed in {elapsed * 1000:.1f}ms")

            # Check performance target (NFR-1)
            if elapsed > 0.2:  # 200ms
                logger.warning(
                    f"⚠️ Performance target exceeded: {filepath} update took "
                    f"{elapsed * 1000:.1f}ms (target: <200ms)"
                )

            return success

        except Exception as e:
            # Update failed - attempt rollback
            logger.error(f"Graph update failed for {filepath}: {e}")

            # Restore old state (best effort)
            try:
                self.graph.remove_relationships_for_file(filepath)
                for rel in old_relationships:
                    self.graph.add_relationship(rel)
                if old_metadata:
                    self.graph.set_file_metadata(filepath, old_metadata)
                logger.info(f"Rolled back changes for {filepath}")
            except Exception as rollback_error:
                logger.error(f"Rollback failed for {filepath}: {rollback_error}")
                logger.error("Graph may be in inconsistent state - validation recommended")

            return False

    def update_on_delete(self, filepath: str) -> bool:
        """Update graph when file is deleted.

        Implements deletion update from TDD Section 3.6.4:
        1. Identify files that depended on deleted file (broken references)
        2. Emit warnings for dependent files
        3. Remove all relationships involving deleted file
        4. Update bidirectional indexes
        5. Mark file as deleted in metadata (EC-14)

        Args:
            filepath: Absolute path to deleted file.

        Returns:
            True if update succeeded, False if update failed.

        Performance Target:
            <200ms per file (NFR-1)
        """
        start_time = time.time()

        # Security: Validate filepath is within project root
        if not self._validate_filepath(filepath):
            logger.warning(f"Rejecting delete for file outside project root: {filepath}")
            return False

        try:
            logger.debug(f"Updating graph for deleted file: {filepath}")

            # Stage 1: Broken reference detection (TDD Section 3.6.4)
            # Get files that imported from the deleted file BEFORE removing relationships
            dependents = self.graph.get_dependents(filepath)
            if dependents:
                self._emit_broken_reference_warnings(filepath, dependents)

            # Stage 2: Remove all relationships
            self.graph.remove_relationships_for_file(filepath)

            # Stage 3: Mark as deleted in metadata (EC-14)
            deletion_timestamp = time.time()
            metadata = FileMetadata(
                filepath=filepath,
                last_analyzed=deletion_timestamp,
                relationship_count=0,
                has_dynamic_patterns=False,
                dynamic_pattern_types=[],
                is_unparseable=False,
                deleted=True,
                deletion_time=deletion_timestamp,
            )
            self.graph.set_file_metadata(filepath, metadata)

            elapsed = time.time() - start_time
            logger.debug(
                f"Graph update for deleted file {filepath} completed in {elapsed * 1000:.1f}ms"
            )

            # Check performance target (NFR-1)
            if elapsed > 0.2:  # 200ms
                logger.warning(
                    f"⚠️ Performance target exceeded: {filepath} deletion update took "
                    f"{elapsed * 1000:.1f}ms (target: <200ms)"
                )

            return True

        except Exception as e:
            logger.error(f"Graph update failed for deleted file {filepath}: {e}")
            return False

    def _emit_broken_reference_warnings(
        self, deleted_file: str, dependents: List[Relationship]
    ) -> None:
        """Emit warnings for files that have broken references to deleted file.

        Implements broken reference detection from TDD Section 3.6.4.

        Args:
            deleted_file: Path to the deleted file.
            dependents: List of relationships where other files depend on deleted_file.
        """
        # Group by source file for cleaner output
        by_source: Dict[str, List[Relationship]] = {}
        for rel in dependents:
            if rel.source_file not in by_source:
                by_source[rel.source_file] = []
            by_source[rel.source_file].append(rel)

        # Emit warning for each importing file
        for source_file, rels in by_source.items():
            # Build list of specific broken imports
            broken_imports = []
            for rel in rels:
                if rel.target_symbol:
                    import_info = (
                        f"{rel.target_symbol} "
                        f"(line {rel.line_number}, type: {rel.relationship_type})"
                    )
                    broken_imports.append(import_info)
                else:
                    broken_imports.append(f"line {rel.line_number} (type: {rel.relationship_type})")

            # Format warning message per TDD Section 3.6.4
            imports_str = ", ".join(broken_imports)
            logger.warning(
                f"⚠️ Imported file deleted: {source_file} imports from {deleted_file} "
                f"which no longer exists. Broken references: {imports_str}"
            )

    def update_on_create(self, filepath: str) -> bool:
        """Update graph when file is created.

        Implements creation update from TDD Section 3.6.3:
        1. Analyze new file
        2. Add relationships to graph
        3. Update bidirectional indexes

        Args:
            filepath: Absolute path to created file.

        Returns:
            True if update succeeded, False if update failed.

        Performance Target:
            <200ms per file (NFR-1)
        """
        start_time = time.time()

        # Security: Validate filepath is within project root
        if not self._validate_filepath(filepath):
            logger.warning(f"Rejecting create for file outside project root: {filepath}")
            return False

        try:
            logger.debug(f"Updating graph for created file: {filepath}")

            # Analyze new file using two-phase analysis (this also adds relationships to graph)
            # Two-phase analysis is always enabled (Issue #133 fix requirement)
            success = self.analyzer.analyze_file_two_phase(
                filepath, relationship_builder=self.relationship_builder
            )

            if not success:
                logger.warning(f"Analysis failed for new file {filepath}")

            elapsed = time.time() - start_time
            logger.debug(
                f"Graph update for created file {filepath} completed in {elapsed * 1000:.1f}ms"
            )

            # Check performance target (NFR-1)
            if elapsed > 0.2:  # 200ms
                logger.warning(
                    f"⚠️ Performance target exceeded: {filepath} creation update took "
                    f"{elapsed * 1000:.1f}ms (target: <200ms)"
                )

            return success

        except Exception as e:
            logger.error(f"Graph update failed for created file {filepath}: {e}")
            return False

    def process_pending_changes(self) -> Dict[str, Any]:
        """Process all pending file changes from FileWatcher.

        This method checks FileWatcher for files with recent timestamps and
        processes each one according to its event type.

        Event type detection:
        - File exists + timestamp: Modified or Created
        - File doesn't exist + timestamp: Deleted

        Returns:
            Dictionary with processing statistics:
            - total: Total files processed
            - modified: Files updated due to modification
            - created: Files added due to creation
            - deleted: Files removed due to deletion
            - failed: Files that failed to process
            - elapsed_ms: Total processing time in milliseconds
        """
        start_time = time.time()

        stats = {
            "total": 0,
            "modified": 0,
            "created": 0,
            "deleted": 0,
            "failed": 0,
            "elapsed_ms": 0.0,
        }

        # Get all files with timestamps
        for filepath, _timestamp in self.file_watcher.file_event_timestamps.items():
            stats["total"] += 1

            # Check if file exists
            path = Path(filepath)
            file_exists = path.exists()

            # Determine event type and process
            if file_exists:
                # File exists - could be modified or created
                # Check if we have metadata for this file
                metadata = self.graph.get_file_metadata(filepath)

                if metadata is None:
                    # No metadata - this is a new file
                    success = self.update_on_create(filepath)
                    if success:
                        stats["created"] += 1
                    else:
                        stats["failed"] += 1
                else:
                    # Has metadata - this is a modification
                    success = self.update_on_modify(filepath)
                    if success:
                        stats["modified"] += 1
                    else:
                        stats["failed"] += 1
            else:
                # File doesn't exist - deletion
                success = self.update_on_delete(filepath)
                if success:
                    stats["deleted"] += 1
                else:
                    stats["failed"] += 1

        # Clear processed timestamps
        self.file_watcher.file_event_timestamps.clear()

        elapsed = time.time() - start_time
        stats["elapsed_ms"] = elapsed * 1000

        logger.info(
            f"Processed {stats['total']} file changes in {stats['elapsed_ms']:.1f}ms: "
            f"{stats['modified']} modified, {stats['created']} created, "
            f"{stats['deleted']} deleted, {stats['failed']} failed"
        )

        return stats
