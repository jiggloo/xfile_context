# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Query API for programmatic access to system state.

This module implements the Query API per TDD Section 3.10.4:
- Programmatic access to system state without parsing files directly
- JSON-compatible return types for all methods
- Type hints for all methods

API Methods (FR-29, FR-18, FR-23):
- get_recent_injections(target_file, limit): Recent context injection events
- get_relationship_graph(): Full graph export structure
- get_dependents(file_path): Files that depend on specified file
- get_dependencies(file_path): Files that specified file depends on
- get_session_metrics(): Current session metrics (in-progress)
- get_cache_statistics(): Current cache statistics

Implementation:
- v0.1.0: Internal Python API (used by MCP server and tests)
- Future: Expose as MCP tools for direct Claude Code access
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .cache import WorkingMemoryCache
    from .injection_logger import InjectionLogger
    from .metrics_collector import MetricsCollector
    from .models import RelationshipGraph
    from .service import CrossFileContextService
    from .warning_logger import WarningLogger


class QueryAPI:
    """Query API for programmatic access to system state.

    Provides a clean interface for querying system state including:
    - Recent context injection events (FR-29)
    - Relationship graph structure (FR-23)
    - File dependencies and dependents (FR-18)
    - Session metrics (in-progress)
    - Cache statistics

    This class can be initialized either with a CrossFileContextService
    (for integrated use) or with individual components (for testing).

    Usage with service:
        service = CrossFileContextService(config)
        api = QueryAPI.from_service(service)
        recent = api.get_recent_injections("/path/to/file.py", limit=10)

    Usage with individual components:
        api = QueryAPI(
            graph=graph,
            cache=cache,
            injection_logger=injection_logger,
            metrics_collector=metrics_collector,
            warning_logger=warning_logger,
            project_root="/path/to/project",
        )
        graph_data = api.get_relationship_graph()
    """

    def __init__(
        self,
        graph: "RelationshipGraph",
        cache: "WorkingMemoryCache",
        injection_logger: "InjectionLogger",
        metrics_collector: "MetricsCollector",
        warning_logger: "WarningLogger",
        project_root: Optional[str] = None,
    ) -> None:
        """Initialize the Query API with system components.

        Args:
            graph: RelationshipGraph instance for dependency queries.
            cache: WorkingMemoryCache instance for cache statistics.
            injection_logger: InjectionLogger instance for injection events.
            metrics_collector: MetricsCollector instance for session metrics.
            warning_logger: WarningLogger instance for warning metrics.
            project_root: Project root directory for relative paths in exports.
        """
        self._graph = graph
        self._cache = cache
        self._injection_logger = injection_logger
        self._metrics_collector = metrics_collector
        self._warning_logger = warning_logger
        self._project_root = project_root

    @classmethod
    def from_service(cls, service: "CrossFileContextService") -> "QueryAPI":
        """Create a QueryAPI instance from a CrossFileContextService.

        This is the recommended way to create a QueryAPI in production use.

        Args:
            service: CrossFileContextService instance.

        Returns:
            QueryAPI instance connected to the service's components.
        """
        return cls(
            graph=service._graph,
            cache=service.cache,
            injection_logger=service._injection_logger,
            metrics_collector=service._metrics_collector,
            warning_logger=service._warning_logger,
            project_root=str(service._project_root),
        )

    def get_recent_injections(
        self,
        target_file: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get recent context injection events (FR-29).

        Returns recent context injection events from the log file,
        useful for debugging and understanding what context Claude received.

        Args:
            target_file: If provided, only return events for this target file.
                        If None, returns all recent events.
            limit: Maximum number of events to return. Default is 10.

        Returns:
            List of injection event dictionaries, most recent first.
            Each dictionary contains:
            - timestamp: ISO 8601 timestamp
            - event_type: "context_injection"
            - source_file: File providing the context
            - target_file: File being read
            - relationship_type: IMPORT, FUNCTION_CALL, or CLASS_INHERITANCE
            - snippet: The injected content
            - snippet_location: File path and line range
            - cache_age_seconds: Age of snippet in cache (None if not cached)
            - cache_hit: True if retrieved from cache
            - token_count: Token count of this snippet
            - context_token_total: Cumulative token count
        """
        from .injection_logger import get_recent_injections

        log_path = self._injection_logger.get_log_path()
        events = get_recent_injections(log_path, target_file, limit)
        return [event.to_dict() for event in events]

    def get_relationship_graph(self) -> Dict[str, Any]:
        """Get the full relationship graph (FR-23).

        Returns the complete graph export per TDD Section 3.10.3.
        Use case: External tools, visualization.

        Returns:
            Dictionary containing:
            - metadata: timestamp, version, language, project_root, counts
            - files: list of file info with paths
            - relationships: list of relationship dicts
            - graph_metadata: circular imports, most connected files
        """
        return self._graph.export_to_dict(project_root=self._project_root)

    def get_dependents(self, file_path: str) -> List[Dict[str, Any]]:
        """Get files that depend on the specified file (FR-18).

        Use case: Impact analysis before editing a file.
        Returns files that import from or otherwise depend on the given file.

        Args:
            file_path: Path to file to query.

        Returns:
            List of relationship dictionaries where file_path is the target.
            Each dictionary contains:
            - source_file: File that depends on file_path
            - target_file: The queried file_path
            - relationship_type: Type of dependency
            - line_number: Line in source_file where dependency exists
            - source_symbol: Symbol in source (if applicable)
            - target_symbol: Symbol being used (if applicable)
            - target_line: Line where symbol is defined (if applicable)
        """
        relationships = self._graph.get_dependents(file_path)
        return [rel.to_dict() for rel in relationships]

    def get_dependencies(self, file_path: str) -> List[Dict[str, Any]]:
        """Get files that the specified file depends on.

        Use case: Understanding a file's context requirements.
        Returns files that the given file imports from or depends on.

        Args:
            file_path: Path to file to query.

        Returns:
            List of relationship dictionaries where file_path is the source.
            Each dictionary contains:
            - source_file: The queried file_path
            - target_file: File that file_path depends on
            - relationship_type: Type of dependency
            - line_number: Line where dependency is declared
            - source_symbol: Symbol in source (if applicable)
            - target_symbol: Symbol being imported (if applicable)
            - target_line: Line where symbol is defined (if applicable)
        """
        relationships = self._graph.get_dependencies(file_path)
        return [rel.to_dict() for rel in relationships]

    def get_session_metrics(self) -> Dict[str, Any]:
        """Get current session metrics (in-progress).

        Returns session metrics built from all system components.
        Use case: Real-time monitoring, debugging.

        Note: This returns the current in-progress metrics. For final
        metrics, call this after session operations are complete.

        Returns:
            Dictionary containing session metrics:
            - session_id: Unique session identifier
            - start_time: Session start timestamp
            - end_time: Current timestamp (session not ended)
            - cache_performance: Hit rate, miss rate, peak size, evictions
            - context_injection: Total injections, token counts, thresholds
            - relationship_graph: File and relationship counts
            - function_usage_distribution: Usage histogram
            - re_read_patterns: Files with multiple re-reads
            - performance: Parsing and injection timing
            - warnings: Warning counts by type
            - identifier_resolution: Resolution statistics
            - configuration: Configuration values captured
        """
        metrics = self._metrics_collector.build_session_metrics(
            cache=self._cache,
            injection_logger=self._injection_logger,
            warning_logger=self._warning_logger,
            graph=self._graph,
        )
        return metrics.to_dict()

    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get current cache statistics.

        Returns cache performance metrics for monitoring.
        Use case: Performance monitoring, cache tuning.

        Returns:
            Dictionary containing:
            - hits: Number of cache hits
            - misses: Number of cache misses
            - staleness_refreshes: Refreshes due to staleness detection
            - evictions_lru: Number of LRU evictions
            - current_size_bytes: Current cache size
            - peak_size_bytes: Peak cache size during session
            - current_entry_count: Current number of entries
            - peak_entry_count: Peak entry count during session
            - hit_rate: Calculated hit rate percentage (0.0-100.0)
        """
        stats = self._cache.get_statistics()
        result = stats.to_dict()

        # Add calculated hit rate for convenience
        result["hit_rate"] = self._cache.get_hit_rate()

        return result

    def get_injection_statistics(self) -> Dict[str, Any]:
        """Get aggregated injection statistics.

        Returns statistics about context injections for the session.

        Returns:
            Dictionary containing:
            - total_injections: Total number of injection events
            - by_relationship_type: Count by relationship type
            - by_source_file: Top source files by injection count
            - total_tokens_injected: Total tokens across all injections
            - cache_hit_count: Number of cache hits
            - cache_miss_count: Number of cache misses
            - cache_hit_rate: Calculated cache hit rate
        """
        stats = self._injection_logger.get_statistics()
        return stats.to_dict()

    def get_warning_statistics(self) -> Dict[str, Any]:
        """Get warning statistics.

        Returns statistics about warnings generated during the session.

        Returns:
            Dictionary containing:
            - total_warnings: Total number of warnings
            - by_type: Count by warning type
            - files_with_most_warnings: Top files by warning count
        """
        stats = self._warning_logger.get_statistics()
        return stats.to_dict()

    def get_graph_statistics(self) -> Dict[str, Any]:
        """Get relationship graph statistics.

        Returns summary statistics about the relationship graph.

        Returns:
            Dictionary containing:
            - total_files: Number of files in graph
            - total_relationships: Number of relationships
            - most_connected_files: Files with most dependents
        """
        graph_export = self.get_relationship_graph()
        metadata = graph_export.get("metadata", {})
        graph_metadata = graph_export.get("graph_metadata", {})

        return {
            "total_files": metadata.get("total_files", 0),
            "total_relationships": metadata.get("total_relationships", 0),
            "most_connected_files": graph_metadata.get("most_connected_files", []),
        }
