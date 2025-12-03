# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Session metrics collection module for comprehensive data-driven tuning.

This module implements the MetricsCollector class per TDD Section 3.4.9 and 3.10.1:
- Aggregate session-level metrics from all system components
- Calculate token count statistics (min, max, median, p95)
- Write metrics to JSONL file at session end
- Capture configuration values for correlation

Log Location: .cross_file_context_logs/session_metrics.jsonl

Related Requirements:
- FR-43 (emit metrics at session end)
- FR-44 (session metrics aggregation)
- FR-45 (JSONL log format)
- FR-46 (metrics structure)
- FR-47 (metrics anonymization - file paths optionally hashed)
- FR-49 (configuration values in metrics)
- T-10.1 through T-10.6 (session metrics tests)
"""

import hashlib
import json
import logging
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO, Tuple

logger = logging.getLogger(__name__)

# Default log directory name (shared with other loggers)
DEFAULT_LOG_DIR = ".cross_file_context_logs"

# Default session metrics log filename
DEFAULT_METRICS_LOG_FILE = "session_metrics.jsonl"


@dataclass
class TokenCountStatistics:
    """Token count statistics for context injection per TDD Section 3.10.1.

    Tracks min, max, median, and p95 token counts to inform threshold tuning.
    """

    min: int = 0
    max: int = 0
    median: int = 0
    p95: int = 0
    total_count: int = 0  # Number of injections tracked

    def to_dict(self) -> Dict[str, int]:
        """Convert to dictionary for JSON serialization."""
        return {
            "min": self.min,
            "max": self.max,
            "median": self.median,
            "p95": self.p95,
        }


@dataclass
class CachePerformanceMetrics:
    """Cache performance metrics per TDD Section 3.10.1.

    Tracks hit rate, miss rate, peak size for cache tuning.
    """

    hit_rate: float = 0.0
    miss_rate: float = 0.0
    total_reads: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    staleness_refreshes: int = 0
    peak_size_kb: float = 0.0
    evictions_lru: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "hit_rate": round(self.hit_rate, 4),
            "miss_rate": round(self.miss_rate, 4),
            "total_reads": self.total_reads,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "staleness_refreshes": self.staleness_refreshes,
            "peak_size_kb": round(self.peak_size_kb, 2),
            "evictions_lru": self.evictions_lru,
        }


@dataclass
class ContextInjectionMetrics:
    """Context injection metrics per TDD Section 3.10.1.

    Tracks token counts and threshold exceedances.
    """

    total_injections: int = 0
    token_counts: TokenCountStatistics = field(default_factory=TokenCountStatistics)
    threshold_exceedances: int = 0  # Injections exceeding token limit

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_injections": self.total_injections,
            "token_counts": self.token_counts.to_dict(),
            "threshold_exceedances": self.threshold_exceedances,
        }


@dataclass
class RelationshipGraphMetrics:
    """Relationship graph metrics per TDD Section 3.10.1.

    Tracks file and relationship counts for understanding codebase structure.
    """

    total_files: int = 0
    total_relationships: int = 0
    most_connected_files: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_files": self.total_files,
            "total_relationships": self.total_relationships,
            "most_connected_files": self.most_connected_files,
        }


@dataclass
class FunctionUsageDistribution:
    """Function usage distribution per TDD Section 3.10.1.

    Histogram of functions by number of files they're used in.
    Validates "functions used in 3+ files" warning threshold (FR-19, FR-20).
    """

    files_1_to_3: int = 0  # Functions used in 1-3 files
    files_4_to_10: int = 0  # Functions used in 4-10 files
    files_11_plus: int = 0  # Functions used in 11+ files

    def to_dict(self) -> Dict[str, int]:
        """Convert to dictionary for JSON serialization."""
        return {
            "1-3_files": self.files_1_to_3,
            "4-10_files": self.files_4_to_10,
            "11+_files": self.files_11_plus,
        }


@dataclass
class PerformanceMetrics:
    """Performance timing metrics per TDD Section 3.10.1.

    Tracks parsing times and injection latency to validate NFR targets.
    """

    parsing_time_ms: TokenCountStatistics = field(default_factory=TokenCountStatistics)
    injection_latency_ms: TokenCountStatistics = field(default_factory=TokenCountStatistics)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "parsing_time_ms": self.parsing_time_ms.to_dict(),
            "injection_latency_ms": self.injection_latency_ms.to_dict(),
        }


@dataclass
class WarningStatisticsMetrics:
    """Warning statistics per TDD Section 3.10.1.

    Tracks warning counts by type for understanding dynamic pattern prevalence.
    """

    total_warnings: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    files_with_most_warnings: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_warnings": self.total_warnings,
            "by_type": self.by_type,
            "files_with_most_warnings": self.files_with_most_warnings,
        }


@dataclass
class IdentifierResolutionMetrics:
    """Identifier resolution effectiveness per TDD Section 3.5.6 and 3.10.1.

    Tracks resolution rates to determine if AST-based resolution is sufficient.
    Decision threshold: If >10% of context injections blocked by unresolved
    identifiers, consider interpreter inspection fallback (v0.2.0+).
    """

    function_calls_analyzed: int = 0
    resolved_to_imports: int = 0
    resolved_to_local: int = 0
    resolved_to_builtin: int = 0
    unresolved: int = 0
    unresolved_needed_for_context: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        total = self.function_calls_analyzed or 1  # Avoid division by zero
        return {
            "function_calls_analyzed": self.function_calls_analyzed,
            "resolved_to_imports": self.resolved_to_imports,
            "resolved_to_imports_pct": round(self.resolved_to_imports / total * 100, 2),
            "resolved_to_local": self.resolved_to_local,
            "resolved_to_local_pct": round(self.resolved_to_local / total * 100, 2),
            "resolved_to_builtin": self.resolved_to_builtin,
            "resolved_to_builtin_pct": round(self.resolved_to_builtin / total * 100, 2),
            "unresolved": self.unresolved,
            "unresolved_pct": round(self.unresolved / total * 100, 2),
            "unresolved_needed_for_context": self.unresolved_needed_for_context,
            "unresolved_needed_for_context_pct": round(
                self.unresolved_needed_for_context / total * 100, 2
            ),
        }


@dataclass
class SessionMetrics:
    """Complete session metrics per TDD Section 3.4.9 and 3.10.1.

    Aggregates all metrics categories for a single session.
    """

    session_id: str = ""
    start_time: str = ""
    end_time: str = ""
    cache_performance: CachePerformanceMetrics = field(default_factory=CachePerformanceMetrics)
    context_injection: ContextInjectionMetrics = field(default_factory=ContextInjectionMetrics)
    relationship_graph: RelationshipGraphMetrics = field(default_factory=RelationshipGraphMetrics)
    function_usage_distribution: FunctionUsageDistribution = field(
        default_factory=FunctionUsageDistribution
    )
    re_read_patterns: List[Dict[str, Any]] = field(default_factory=list)
    performance: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    warnings: WarningStatisticsMetrics = field(default_factory=WarningStatisticsMetrics)
    identifier_resolution: IdentifierResolutionMetrics = field(
        default_factory=IdentifierResolutionMetrics
    )
    configuration: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "cache_performance": self.cache_performance.to_dict(),
            "context_injection": self.context_injection.to_dict(),
            "relationship_graph": self.relationship_graph.to_dict(),
            "function_usage_distribution": self.function_usage_distribution.to_dict(),
            "re_read_patterns": self.re_read_patterns,
            "performance": self.performance.to_dict(),
            "warnings": self.warnings.to_dict(),
            "identifier_resolution": self.identifier_resolution.to_dict(),
            "configuration": self.configuration,
        }


def calculate_percentile_statistics(values: List[int]) -> TokenCountStatistics:
    """Calculate min, max, median, and p95 from a list of values.

    Args:
        values: List of integer values (e.g., token counts or timing in ms).

    Returns:
        TokenCountStatistics with computed statistics.
    """
    if not values:
        return TokenCountStatistics()

    sorted_values = sorted(values)
    n = len(sorted_values)

    # Calculate p95 index (95th percentile)
    # For n=100, p95_idx = 94 (95th value)
    p95_idx = int(n * 0.95)
    if p95_idx >= n:
        p95_idx = n - 1

    return TokenCountStatistics(
        min=sorted_values[0],
        max=sorted_values[-1],
        median=int(statistics.median(sorted_values)),
        p95=sorted_values[p95_idx],
        total_count=n,
    )


def anonymize_filepath(filepath: str) -> str:
    """Anonymize a file path using SHA-256 hash per FR-47.

    Produces a consistent hash that can be correlated across sessions
    but doesn't reveal the actual file path.

    Args:
        filepath: File path to anonymize.

    Returns:
        Hashed file path (first 16 chars of SHA-256).
    """
    hash_bytes = hashlib.sha256(filepath.encode("utf-8")).hexdigest()
    return f"file_{hash_bytes[:16]}"


class MetricsCollector:
    """Collector for aggregating session metrics.

    Collects metrics from all system components throughout a session and
    writes comprehensive metrics to JSONL at session end per TDD Section 3.10.1.

    Features:
    - Session lifecycle tracking (start/end time, session ID)
    - Token count tracking with percentile calculation
    - Integration with cache, injection logger, warning logger
    - JSONL output for machine-parseable analysis
    - Optional file path anonymization

    Usage:
        collector = MetricsCollector()

        # Record events during session
        collector.record_injection_token_count(150)
        collector.record_parsing_time_ms(45)

        # At session end, collect from subsystems and write
        collector.collect_cache_metrics(cache)
        collector.collect_injection_metrics(injection_logger)
        collector.collect_warning_metrics(warning_logger)
        collector.collect_graph_metrics(graph)
        collector.finalize_and_write()

    Context manager usage:
        with MetricsCollector() as collector:
            # ... session operations ...
        # Metrics automatically written on exit
    """

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        log_file: Optional[str] = None,
        anonymize_paths: bool = False,
        session_id: Optional[str] = None,
    ) -> None:
        """Initialize the metrics collector.

        Args:
            log_dir: Directory for log files. If None, uses current working
                    directory + .cross_file_context_logs/
            log_file: Log filename. If None, uses session_metrics.jsonl.
                     Must be a simple filename without path separators.
            anonymize_paths: If True, hash file paths in metrics (FR-47).
            session_id: Optional session ID. If None, generates a UUID.

        Raises:
            ValueError: If log_file contains path separators.
        """
        if log_dir is None:
            log_dir = Path.cwd() / DEFAULT_LOG_DIR
        self._log_dir = Path(log_dir)

        # Validate log_file doesn't contain path components (security)
        log_file = log_file or DEFAULT_METRICS_LOG_FILE
        if "/" in log_file or "\\" in log_file or ":" in log_file:
            raise ValueError(f"log_file must be a filename only, not a path: {log_file}")
        self._log_file = log_file

        self._anonymize_paths = anonymize_paths

        # Initialize session
        self._session_id = session_id or str(uuid.uuid4())
        self._start_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

        # Token count tracking (for percentile calculation)
        self._token_counts: List[int] = []
        self._parsing_times_ms: List[int] = []
        self._injection_latencies_ms: List[int] = []

        # Re-read pattern tracking
        self._file_read_counts: Dict[str, int] = {}

        # Threshold exceedance count
        self._threshold_exceedances = 0

        # Configuration values to capture
        self._configuration: Dict[str, Any] = {}

        # Identifier resolution tracking
        self._identifier_resolution = IdentifierResolutionMetrics()

        # File handle (lazy initialization)
        self._file_handle: Optional[TextIO] = None

        logger.debug(
            f"MetricsCollector initialized with session_id={self._session_id}, "
            f"anonymize_paths={anonymize_paths}"
        )

    def _ensure_log_dir(self) -> None:
        """Create log directory if it doesn't exist."""
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_path(self) -> Path:
        """Get full path to the log file.

        Returns:
            Path to the session metrics log file.
        """
        return self._log_dir / self._log_file

    def _maybe_anonymize(self, filepath: str) -> str:
        """Anonymize filepath if anonymization is enabled.

        Args:
            filepath: File path to potentially anonymize.

        Returns:
            Original or anonymized file path.
        """
        if self._anonymize_paths:
            return anonymize_filepath(filepath)
        return filepath

    def record_injection_token_count(
        self, token_count: int, exceeded_threshold: bool = False
    ) -> None:
        """Record a token count from a context injection.

        Call this for each context injection to track token usage statistics.

        Args:
            token_count: Number of tokens in the injected context.
            exceeded_threshold: True if this injection exceeded the token limit.
        """
        self._token_counts.append(token_count)
        if exceeded_threshold:
            self._threshold_exceedances += 1

    def record_parsing_time_ms(self, time_ms: int) -> None:
        """Record a file parsing time.

        Args:
            time_ms: Parsing time in milliseconds.
        """
        self._parsing_times_ms.append(time_ms)

    def record_injection_latency_ms(self, latency_ms: int) -> None:
        """Record a context injection latency.

        Args:
            latency_ms: Injection latency in milliseconds.
        """
        self._injection_latencies_ms.append(latency_ms)

    def record_file_read(self, filepath: str) -> None:
        """Record a file read for re-read pattern tracking.

        Args:
            filepath: Path of the file that was read.
        """
        path = self._maybe_anonymize(filepath)
        self._file_read_counts[path] = self._file_read_counts.get(path, 0) + 1

    def record_identifier_resolution(
        self,
        resolved_to_import: bool = False,
        resolved_to_local: bool = False,
        resolved_to_builtin: bool = False,
        unresolved: bool = False,
        needed_for_context: bool = False,
    ) -> None:
        """Record an identifier resolution attempt.

        Args:
            resolved_to_import: Resolved to an import.
            resolved_to_local: Resolved to a local definition.
            resolved_to_builtin: Resolved to a Python builtin.
            unresolved: Could not be resolved.
            needed_for_context: Unresolved and blocked context injection.
        """
        self._identifier_resolution.function_calls_analyzed += 1

        if resolved_to_import:
            self._identifier_resolution.resolved_to_imports += 1
        elif resolved_to_local:
            self._identifier_resolution.resolved_to_local += 1
        elif resolved_to_builtin:
            self._identifier_resolution.resolved_to_builtin += 1
        elif unresolved:
            self._identifier_resolution.unresolved += 1
            if needed_for_context:
                self._identifier_resolution.unresolved_needed_for_context += 1

    def set_configuration(self, config: Dict[str, Any]) -> None:
        """Set configuration values to capture in metrics per FR-49.

        Args:
            config: Dictionary of configuration values.
        """
        self._configuration = config.copy()

    def collect_cache_metrics(self, cache: Any) -> CachePerformanceMetrics:
        """Collect cache performance metrics from WorkingMemoryCache.

        Args:
            cache: WorkingMemoryCache instance.

        Returns:
            CachePerformanceMetrics with collected data.
        """
        stats = cache.get_statistics()

        total_reads = stats.hits + stats.misses + stats.staleness_refreshes
        hit_rate = stats.hits / total_reads if total_reads > 0 else 0.0
        miss_rate = stats.misses / total_reads if total_reads > 0 else 0.0

        return CachePerformanceMetrics(
            hit_rate=hit_rate,
            miss_rate=miss_rate,
            total_reads=total_reads,
            cache_hits=stats.hits,
            cache_misses=stats.misses,
            staleness_refreshes=stats.staleness_refreshes,
            peak_size_kb=stats.peak_size_bytes / 1024,
            evictions_lru=stats.evictions_lru,
        )

    def collect_injection_metrics(self, injection_logger: Any) -> ContextInjectionMetrics:
        """Collect context injection metrics from InjectionLogger.

        Args:
            injection_logger: InjectionLogger instance.

        Returns:
            ContextInjectionMetrics with collected data.
        """
        stats = injection_logger.get_statistics()

        # Calculate token count statistics from recorded values
        token_stats = calculate_percentile_statistics(self._token_counts)

        return ContextInjectionMetrics(
            total_injections=stats.total_injections,
            token_counts=token_stats,
            threshold_exceedances=self._threshold_exceedances,
        )

    def collect_warning_metrics(self, warning_logger: Any) -> WarningStatisticsMetrics:
        """Collect warning statistics from WarningLogger.

        Args:
            warning_logger: WarningLogger instance.

        Returns:
            WarningStatisticsMetrics with collected data.
        """
        stats = warning_logger.get_statistics()

        # Anonymize file paths in files_with_most_warnings if needed
        files_with_warnings = []
        for item in stats.files_with_most_warnings:
            files_with_warnings.append(
                {
                    "file": self._maybe_anonymize(item["file"]),
                    "warning_count": item["warning_count"],
                }
            )

        return WarningStatisticsMetrics(
            total_warnings=stats.total_warnings,
            by_type=stats.by_type,
            files_with_most_warnings=files_with_warnings,
        )

    def collect_graph_metrics(
        self, graph: Any
    ) -> Tuple[RelationshipGraphMetrics, FunctionUsageDistribution]:
        """Collect relationship graph metrics.

        Args:
            graph: RelationshipGraph instance.

        Returns:
            Tuple of (RelationshipGraphMetrics, FunctionUsageDistribution).
        """
        # Get graph statistics
        all_relationships = graph.get_all_relationships()
        total_relationships = len(all_relationships)

        # Get unique files
        files = set()
        for rel in all_relationships:
            files.add(rel.source_file)
            files.add(rel.target_file)
        total_files = len(files)

        # Calculate most connected files (by dependency count)
        dependency_counts: Dict[str, int] = {}
        for rel in all_relationships:
            dependency_counts[rel.target_file] = dependency_counts.get(rel.target_file, 0) + 1

        # Sort by count and get top 5
        sorted_files = sorted(dependency_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        most_connected = [
            {"file": self._maybe_anonymize(f), "dependency_count": c} for f, c in sorted_files
        ]

        # Calculate function usage distribution
        # Count how many files use each function/symbol
        symbol_usage: Dict[Tuple[str, Optional[str]], set[str]] = {}
        for rel in all_relationships:
            if rel.target_symbol:
                key = (rel.target_file, rel.target_symbol)
                if key not in symbol_usage:
                    symbol_usage[key] = set()
                symbol_usage[key].add(rel.source_file)

        # Categorize into buckets
        files_1_to_3 = 0
        files_4_to_10 = 0
        files_11_plus = 0

        for using_files in symbol_usage.values():
            count = len(using_files)
            if count <= 3:
                files_1_to_3 += 1
            elif count <= 10:
                files_4_to_10 += 1
            else:
                files_11_plus += 1

        graph_metrics = RelationshipGraphMetrics(
            total_files=total_files,
            total_relationships=total_relationships,
            most_connected_files=most_connected,
        )

        usage_distribution = FunctionUsageDistribution(
            files_1_to_3=files_1_to_3,
            files_4_to_10=files_4_to_10,
            files_11_plus=files_11_plus,
        )

        return graph_metrics, usage_distribution

    def get_re_read_patterns(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Get files with multiple re-reads.

        Args:
            top_n: Number of top files to return.

        Returns:
            List of dicts with file and read_count.
        """
        # Filter to files read more than once
        re_reads = [(f, c) for f, c in self._file_read_counts.items() if c > 1]

        # Sort by count descending
        sorted_re_reads = sorted(re_reads, key=lambda x: x[1], reverse=True)[:top_n]

        return [{"file": f, "read_count": c} for f, c in sorted_re_reads]

    def build_session_metrics(
        self,
        cache: Optional[Any] = None,
        injection_logger: Optional[Any] = None,
        warning_logger: Optional[Any] = None,
        graph: Optional[Any] = None,
    ) -> SessionMetrics:
        """Build complete session metrics from all sources.

        Args:
            cache: WorkingMemoryCache instance.
            injection_logger: InjectionLogger instance.
            warning_logger: WarningLogger instance.
            graph: RelationshipGraph instance.

        Returns:
            SessionMetrics with all collected data.
        """
        end_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

        metrics = SessionMetrics(
            session_id=self._session_id,
            start_time=self._start_time,
            end_time=end_time,
            configuration=self._configuration,
            identifier_resolution=self._identifier_resolution,
        )

        # Collect cache metrics
        if cache is not None:
            metrics.cache_performance = self.collect_cache_metrics(cache)

        # Collect injection metrics
        if injection_logger is not None:
            metrics.context_injection = self.collect_injection_metrics(injection_logger)

        # Collect warning metrics
        if warning_logger is not None:
            metrics.warnings = self.collect_warning_metrics(warning_logger)

        # Collect graph metrics
        if graph is not None:
            graph_metrics, usage_dist = self.collect_graph_metrics(graph)
            metrics.relationship_graph = graph_metrics
            metrics.function_usage_distribution = usage_dist

        # Add re-read patterns
        metrics.re_read_patterns = self.get_re_read_patterns()

        # Add performance metrics
        metrics.performance = PerformanceMetrics(
            parsing_time_ms=calculate_percentile_statistics(self._parsing_times_ms),
            injection_latency_ms=calculate_percentile_statistics(self._injection_latencies_ms),
        )

        return metrics

    def write_metrics(self, metrics: SessionMetrics) -> None:
        """Write session metrics to JSONL file.

        Args:
            metrics: SessionMetrics to write.
        """
        self._ensure_log_dir()
        log_path = self._get_log_path()

        # Open file for appending
        with open(log_path, "a", encoding="utf-8") as f:
            json_line = json.dumps(metrics.to_dict(), separators=(",", ":"))
            f.write(json_line + "\n")

        logger.info(f"Session metrics written to {log_path}")

    def finalize_and_write(
        self,
        cache: Optional[Any] = None,
        injection_logger: Optional[Any] = None,
        warning_logger: Optional[Any] = None,
        graph: Optional[Any] = None,
    ) -> SessionMetrics:
        """Finalize session and write metrics to file.

        Convenience method that builds and writes metrics in one call.

        Args:
            cache: WorkingMemoryCache instance.
            injection_logger: InjectionLogger instance.
            warning_logger: WarningLogger instance.
            graph: RelationshipGraph instance.

        Returns:
            The SessionMetrics that were written.
        """
        metrics = self.build_session_metrics(
            cache=cache,
            injection_logger=injection_logger,
            warning_logger=warning_logger,
            graph=graph,
        )
        self.write_metrics(metrics)
        return metrics

    def get_log_path(self) -> Path:
        """Get the path to the log file.

        Returns:
            Path to the session metrics log file.
        """
        return self._get_log_path()

    def get_session_id(self) -> str:
        """Get the current session ID.

        Returns:
            Session ID string.
        """
        return self._session_id

    def __enter__(self) -> "MetricsCollector":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - metrics are NOT automatically written.

        To write metrics on exit, call finalize_and_write() before exiting,
        or use the close() method with components.
        """
        pass  # Metrics must be explicitly written with finalize_and_write()


def read_session_metrics(log_path: Path, limit: Optional[int] = None) -> List[SessionMetrics]:
    """Read session metrics from a JSONL log file.

    Utility function for reading back logged metrics, useful for
    testing and analysis.

    Args:
        log_path: Path to the session_metrics.jsonl file.
        limit: Optional maximum number of sessions to read.

    Returns:
        List of SessionMetrics objects.

    Raises:
        FileNotFoundError: If log file doesn't exist.
    """
    if not log_path.exists():
        return []

    metrics_list: List[SessionMetrics] = []

    with open(log_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit is not None and i >= limit:
                break

            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                # Create SessionMetrics from dict
                metrics = SessionMetrics(
                    session_id=data.get("session_id", ""),
                    start_time=data.get("start_time", ""),
                    end_time=data.get("end_time", ""),
                    configuration=data.get("configuration", {}),
                )

                # Populate nested metrics if present
                if "cache_performance" in data:
                    cp = data["cache_performance"]
                    metrics.cache_performance = CachePerformanceMetrics(
                        hit_rate=cp.get("hit_rate", 0.0),
                        miss_rate=cp.get("miss_rate", 0.0),
                        total_reads=cp.get("total_reads", 0),
                        cache_hits=cp.get("cache_hits", 0),
                        cache_misses=cp.get("cache_misses", 0),
                        staleness_refreshes=cp.get("staleness_refreshes", 0),
                        peak_size_kb=cp.get("peak_size_kb", 0.0),
                        evictions_lru=cp.get("evictions_lru", 0),
                    )

                if "context_injection" in data:
                    ci = data["context_injection"]
                    tc = ci.get("token_counts", {})
                    metrics.context_injection = ContextInjectionMetrics(
                        total_injections=ci.get("total_injections", 0),
                        token_counts=TokenCountStatistics(
                            min=tc.get("min", 0),
                            max=tc.get("max", 0),
                            median=tc.get("median", 0),
                            p95=tc.get("p95", 0),
                        ),
                        threshold_exceedances=ci.get("threshold_exceedances", 0),
                    )

                if "relationship_graph" in data:
                    rg = data["relationship_graph"]
                    metrics.relationship_graph = RelationshipGraphMetrics(
                        total_files=rg.get("total_files", 0),
                        total_relationships=rg.get("total_relationships", 0),
                        most_connected_files=rg.get("most_connected_files", []),
                    )

                if "function_usage_distribution" in data:
                    fud = data["function_usage_distribution"]
                    metrics.function_usage_distribution = FunctionUsageDistribution(
                        files_1_to_3=fud.get("1-3_files", 0),
                        files_4_to_10=fud.get("4-10_files", 0),
                        files_11_plus=fud.get("11+_files", 0),
                    )

                if "re_read_patterns" in data:
                    metrics.re_read_patterns = data["re_read_patterns"]

                if "warnings" in data:
                    w = data["warnings"]
                    metrics.warnings = WarningStatisticsMetrics(
                        total_warnings=w.get("total_warnings", 0),
                        by_type=w.get("by_type", {}),
                        files_with_most_warnings=w.get("files_with_most_warnings", []),
                    )

                metrics_list.append(metrics)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Skipping malformed metrics entry: {e}")
                continue

    return metrics_list
