# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Metrics Analysis Tool for cross-file context session metrics.

Analyzes session metrics JSONL files to identify patterns and suggest
optimal configuration values per TDD Section 3.10.6.

Features:
- Parse session metrics JSONL files
- Compute aggregate statistics across sessions
- Identify outliers and patterns
- Suggest optimal configuration values
- Human-readable report output

Usage:
    python scripts/analyze_metrics.py .cross_file_context_logs/session_metrics.jsonl
    python scripts/analyze_metrics.py path/to/metrics1.jsonl path/to/metrics2.jsonl

Related Requirements:
- FR-48 (metrics analysis tool)
- T-10.7 (analysis tool functionality)
"""

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class AggregateStatistics:
    """Aggregate statistics across multiple sessions."""

    # Cache performance
    avg_hit_rate: float = 0.0
    avg_peak_size_kb: float = 0.0
    total_evictions_lru: int = 0
    avg_youngest_evicted_age_seconds: Optional[float] = None

    # Context injection
    token_min: int = 0
    token_median: int = 0
    token_p95: int = 0
    token_max: int = 0
    total_injections: int = 0
    total_threshold_exceedances: int = 0

    # Performance
    parsing_median_ms: int = 0
    parsing_p95_ms: int = 0
    injection_median_ms: int = 0
    injection_p95_ms: int = 0

    # Warnings
    total_warnings: int = 0
    warnings_by_type: Dict[str, int] = field(default_factory=dict)
    files_with_most_warnings: List[Dict[str, Any]] = field(default_factory=list)

    # Relationship graph
    avg_total_files: float = 0.0
    avg_total_relationships: float = 0.0

    # Function usage
    total_functions_1_to_3: int = 0
    total_functions_4_to_10: int = 0
    total_functions_11_plus: int = 0

    # Re-read patterns
    files_with_re_reads: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ConfigurationRecommendation:
    """A configuration recommendation based on metrics analysis."""

    parameter: str
    current_value: Any
    recommended_value: Optional[Any]
    reason: str
    confidence: str  # "high", "medium", "low"


@dataclass
class AnalysisReport:
    """Complete analysis report."""

    sessions_analyzed: int
    date_range: Tuple[str, str]
    statistics: AggregateStatistics
    recommendations: List[ConfigurationRecommendation]
    outliers: List[str]
    performance_status: Dict[str, bool]


def parse_session_metrics(file_path: Path) -> List[Dict[str, Any]]:
    """Parse session metrics from a JSONL file.

    Args:
        file_path: Path to the session_metrics.jsonl file.

    Returns:
        List of session metrics dictionaries.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file contains no valid entries.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Metrics file not found: {file_path}")

    sessions: List[Dict[str, Any]] = []

    with open(file_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                sessions.append(data)
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping malformed entry at line {line_num}: {e}", file=sys.stderr)
                continue

    return sessions


def compute_aggregate_statistics(sessions: List[Dict[str, Any]]) -> AggregateStatistics:
    """Compute aggregate statistics across all sessions.

    Args:
        sessions: List of session metrics dictionaries.

    Returns:
        AggregateStatistics with computed values.
    """
    stats = AggregateStatistics()

    if not sessions:
        return stats

    # Cache performance aggregation
    hit_rates: List[float] = []
    peak_sizes: List[float] = []
    total_evictions = 0

    for session in sessions:
        cache = session.get("cache_performance", {})
        hit_rate = cache.get("hit_rate", 0.0)
        # Only include hit rates from sessions with actual reads
        if cache.get("total_reads", 0) > 0:
            hit_rates.append(hit_rate)
        peak_sizes.append(cache.get("peak_size_kb", 0.0))
        total_evictions += cache.get("evictions_lru", 0)

    stats.avg_hit_rate = statistics.mean(hit_rates) if hit_rates else 0.0
    stats.avg_peak_size_kb = statistics.mean(peak_sizes) if peak_sizes else 0.0
    stats.total_evictions_lru = total_evictions

    # Token count aggregation
    all_token_mins: List[int] = []
    all_token_maxs: List[int] = []
    all_token_medians: List[int] = []
    all_token_p95s: List[int] = []
    total_injections = 0
    total_exceedances = 0

    for session in sessions:
        ci = session.get("context_injection", {})
        tc = ci.get("token_counts", {})

        # Only include sessions with actual injections
        if ci.get("total_injections", 0) > 0:
            all_token_mins.append(tc.get("min", 0))
            all_token_maxs.append(tc.get("max", 0))
            all_token_medians.append(tc.get("median", 0))
            all_token_p95s.append(tc.get("p95", 0))

        total_injections += ci.get("total_injections", 0)
        total_exceedances += ci.get("threshold_exceedances", 0)

    if all_token_mins:
        stats.token_min = min(all_token_mins)
        stats.token_max = max(all_token_maxs)
        stats.token_median = int(statistics.median(all_token_medians))
        stats.token_p95 = int(statistics.median(all_token_p95s))

    stats.total_injections = total_injections
    stats.total_threshold_exceedances = total_exceedances

    # Performance aggregation
    parsing_medians: List[int] = []
    parsing_p95s: List[int] = []
    injection_medians: List[int] = []
    injection_p95s: List[int] = []

    for session in sessions:
        perf = session.get("performance", {})
        parsing = perf.get("parsing_time_ms", {})
        injection = perf.get("injection_latency_ms", {})

        # Only include sessions with actual parsing
        if parsing.get("median", 0) > 0:
            parsing_medians.append(parsing.get("median", 0))
            parsing_p95s.append(parsing.get("p95", 0))

        if injection.get("median", 0) > 0:
            injection_medians.append(injection.get("median", 0))
            injection_p95s.append(injection.get("p95", 0))

    if parsing_medians:
        stats.parsing_median_ms = int(statistics.median(parsing_medians))
        stats.parsing_p95_ms = int(statistics.median(parsing_p95s))

    if injection_medians:
        stats.injection_median_ms = int(statistics.median(injection_medians))
        stats.injection_p95_ms = int(statistics.median(injection_p95s))

    # Warning aggregation
    warnings_by_type: Dict[str, int] = {}
    files_warnings: Dict[str, int] = {}
    total_warnings = 0

    for session in sessions:
        warnings = session.get("warnings", {})
        total_warnings += warnings.get("total_warnings", 0)

        for warn_type, count in warnings.get("by_type", {}).items():
            warnings_by_type[warn_type] = warnings_by_type.get(warn_type, 0) + count

        for file_warn in warnings.get("files_with_most_warnings", []):
            file_path = file_warn.get("file", "")
            warn_count = file_warn.get("warning_count", 0)
            files_warnings[file_path] = files_warnings.get(file_path, 0) + warn_count

    stats.total_warnings = total_warnings
    stats.warnings_by_type = warnings_by_type

    # Get top files with warnings
    sorted_files = sorted(files_warnings.items(), key=lambda x: x[1], reverse=True)[:5]
    stats.files_with_most_warnings = [{"file": f, "warning_count": c} for f, c in sorted_files]

    # Relationship graph aggregation
    total_files: List[int] = []
    total_rels: List[int] = []

    for session in sessions:
        rg = session.get("relationship_graph", {})
        total_files.append(rg.get("total_files", 0))
        total_rels.append(rg.get("total_relationships", 0))

    stats.avg_total_files = statistics.mean(total_files) if total_files else 0.0
    stats.avg_total_relationships = statistics.mean(total_rels) if total_rels else 0.0

    # Function usage aggregation
    for session in sessions:
        fud = session.get("function_usage_distribution", {})
        stats.total_functions_1_to_3 += fud.get("1-3_files", 0)
        stats.total_functions_4_to_10 += fud.get("4-10_files", 0)
        stats.total_functions_11_plus += fud.get("11+_files", 0)

    # Re-read pattern aggregation
    re_read_files: Dict[str, int] = {}
    for session in sessions:
        for pattern in session.get("re_read_patterns", []):
            file_path = pattern.get("file", "")
            read_count = pattern.get("read_count", 0)
            if file_path:
                re_read_files[file_path] = re_read_files.get(file_path, 0) + read_count

    sorted_re_reads = sorted(re_read_files.items(), key=lambda x: x[1], reverse=True)[:10]
    stats.files_with_re_reads = [{"file": f, "read_count": c} for f, c in sorted_re_reads]

    return stats


def identify_outliers(sessions: List[Dict[str, Any]], stats: AggregateStatistics) -> List[str]:
    """Identify outlier sessions and patterns.

    Args:
        sessions: List of session metrics.
        stats: Aggregate statistics for comparison.

    Returns:
        List of outlier descriptions.
    """
    outliers: List[str] = []

    for session in sessions:
        session_id = session.get("session_id", "unknown")[:8]

        # Low cache hit rate (< 50% when avg is > 60%)
        cache = session.get("cache_performance", {})
        hit_rate = cache.get("hit_rate", 0.0)
        if cache.get("total_reads", 0) > 10 and hit_rate < 0.5 and stats.avg_hit_rate > 0.6:
            avg_rate = stats.avg_hit_rate
            outliers.append(
                f"Session {session_id}: Low cache hit rate ({hit_rate:.1%} vs avg {avg_rate:.1%})"
            )

        # Excessive threshold exceedances (> 5%)
        ci = session.get("context_injection", {})
        total_inj = ci.get("total_injections", 0)
        exceedances = ci.get("threshold_exceedances", 0)
        if total_inj > 10 and exceedances / total_inj > 0.05:
            exceed_pct = exceedances / total_inj
            outliers.append(
                f"Session {session_id}: High threshold exceedances "
                f"({exceedances}/{total_inj} = {exceed_pct:.1%})"
            )

        # Slow performance (p95 > 2x target)
        perf = session.get("performance", {})
        parsing_p95 = perf.get("parsing_time_ms", {}).get("p95", 0)
        injection_p95 = perf.get("injection_latency_ms", {}).get("p95", 0)

        if parsing_p95 > 400:  # > 2x of 200ms target
            outliers.append(
                f"Session {session_id}: Slow parsing (p95={parsing_p95}ms, target=<200ms)"
            )

        if injection_p95 > 100:  # > 2x of 50ms target
            outliers.append(
                f"Session {session_id}: Slow injection (p95={injection_p95}ms, target=<50ms)"
            )

    # Also check for files with excessive re-reads
    for re_read in stats.files_with_re_reads:
        if re_read["read_count"] > 10:
            file_name = Path(re_read["file"]).name if "/" in re_read["file"] else re_read["file"]
            outliers.append(f"File {file_name}: Excessive re-reads ({re_read['read_count']})")

    return outliers


def generate_recommendations(
    sessions: List[Dict[str, Any]], stats: AggregateStatistics
) -> List[ConfigurationRecommendation]:
    """Generate configuration recommendations based on metrics.

    Args:
        sessions: List of session metrics.
        stats: Aggregate statistics.

    Returns:
        List of configuration recommendations.
    """
    recommendations: List[ConfigurationRecommendation] = []

    # Get current configuration from most recent session
    current_config: Dict[str, Any] = {}
    if sessions:
        current_config = sessions[-1].get("configuration", {})

    # Cache expiry recommendation
    current_expiry = current_config.get("cache_expiry_minutes", 10)
    if stats.avg_hit_rate < 0.5 and stats.total_evictions_lru > 0:
        # Low hit rate with evictions suggests cache too small or expiry too short
        recommendations.append(
            ConfigurationRecommendation(
                parameter="cache_expiry_minutes",
                current_value=current_expiry,
                recommended_value=max(current_expiry, 15),
                reason=(
                    f"Low cache hit rate ({stats.avg_hit_rate:.1%}) with evictions "
                    "may benefit from longer expiry"
                ),
                confidence="medium",
            )
        )
    elif stats.avg_hit_rate > 0.8 and stats.total_evictions_lru == 0:
        # High hit rate with no evictions - expiry might be fine or could be reduced
        recommendations.append(
            ConfigurationRecommendation(
                parameter="cache_expiry_minutes",
                current_value=current_expiry,
                recommended_value=None,
                reason=f"Cache hit rate ({stats.avg_hit_rate:.1%}) is good, expiry is adequate",
                confidence="high",
            )
        )

    # Cache size recommendation
    current_size = current_config.get("cache_size_limit_kb", 50)
    if stats.total_evictions_lru > 10 and stats.avg_peak_size_kb >= current_size * 0.9:
        # Many evictions and hitting size limit
        recommendations.append(
            ConfigurationRecommendation(
                parameter="cache_size_limit_kb",
                current_value=current_size,
                recommended_value=int(current_size * 1.5),
                reason=(
                    f"Frequent LRU evictions ({stats.total_evictions_lru}) and "
                    f"peak usage near limit ({stats.avg_peak_size_kb:.1f}KB)"
                ),
                confidence="high",
            )
        )
    else:
        recommendations.append(
            ConfigurationRecommendation(
                parameter="cache_size_limit_kb",
                current_value=current_size,
                recommended_value=None,
                reason=f"Cache size adequate (peak: {stats.avg_peak_size_kb:.1f}KB avg)",
                confidence="high",
            )
        )

    # Token limit recommendation
    current_token_limit = current_config.get("context_token_limit", 500)
    exceedance_rate = (
        stats.total_threshold_exceedances / stats.total_injections
        if stats.total_injections > 0
        else 0
    )

    if exceedance_rate > 0.05:
        # More than 5% exceedances
        recommendations.append(
            ConfigurationRecommendation(
                parameter="context_token_limit",
                current_value=current_token_limit,
                recommended_value=int(stats.token_p95 * 1.2) if stats.token_p95 > 0 else None,
                reason=f"High exceedance rate ({exceedance_rate:.1%}), p95={stats.token_p95}",
                confidence="high",
            )
        )
    elif stats.token_p95 < current_token_limit * 0.8:
        # p95 well below limit
        recommendations.append(
            ConfigurationRecommendation(
                parameter="context_token_limit",
                current_value=current_token_limit,
                recommended_value=None,
                reason=f"{current_token_limit}-token limit is appropriate (p95={stats.token_p95})",
                confidence="high",
            )
        )

    # Function usage threshold recommendation
    current_threshold = current_config.get("function_usage_warning_threshold", 3)
    total_functions = (
        stats.total_functions_1_to_3 + stats.total_functions_4_to_10 + stats.total_functions_11_plus
    )

    if total_functions > 0:
        pct_low_usage = stats.total_functions_1_to_3 / total_functions
        if pct_low_usage > 0.9:
            recommendations.append(
                ConfigurationRecommendation(
                    parameter="function_usage_warning_threshold",
                    current_value=current_threshold,
                    recommended_value=None,
                    reason=(
                        f"Threshold of {current_threshold} is appropriate "
                        f"({pct_low_usage:.0%} of functions used in <=3 files)"
                    ),
                    confidence="high",
                )
            )
        elif pct_low_usage < 0.7:
            recommendations.append(
                ConfigurationRecommendation(
                    parameter="function_usage_warning_threshold",
                    current_value=current_threshold,
                    recommended_value=max(current_threshold + 1, 4),
                    reason=(
                        f"Many functions used in 4+ files ({1-pct_low_usage:.0%}), "
                        "consider raising threshold"
                    ),
                    confidence="medium",
                )
            )

    return recommendations


def check_performance_targets(stats: AggregateStatistics) -> Dict[str, bool]:
    """Check if performance meets NFR targets.

    Args:
        stats: Aggregate statistics.

    Returns:
        Dictionary mapping target name to whether it's met.
    """
    return {
        "parsing_p95_under_200ms": stats.parsing_p95_ms <= 200 or stats.parsing_p95_ms == 0,
        "injection_p95_under_50ms": stats.injection_p95_ms <= 50 or stats.injection_p95_ms == 0,
    }


def format_report(report: AnalysisReport) -> str:
    """Format the analysis report as human-readable text.

    Args:
        report: The analysis report to format.

    Returns:
        Formatted report string.
    """
    lines: List[str] = []
    stats = report.statistics

    # Header
    lines.append(f"Session Metrics Analysis ({report.sessions_analyzed} sessions analyzed)")
    lines.append("=" * 60)
    lines.append("")

    # Date range
    if report.date_range[0] and report.date_range[1]:
        lines.append(f"Date Range: {report.date_range[0][:10]} to {report.date_range[1][:10]}")
        lines.append("")

    # Cache Performance
    lines.append("Cache Performance:")
    lines.append(f"  Average hit rate: {stats.avg_hit_rate:.0%}")
    lines.append(f"  Peak size: {stats.avg_peak_size_kb:.1f} KB (avg)")
    lines.append(f"  LRU evictions: {stats.total_evictions_lru}")

    # Find cache recommendation
    cache_recs = [r for r in report.recommendations if "cache" in r.parameter.lower()]
    for rec in cache_recs:
        if rec.recommended_value is not None:
            lines.append(f"  -> RECOMMENDATION: {rec.reason}")
        else:
            lines.append(f"  -> {rec.reason}")
    lines.append("")

    # Context Injection
    lines.append("Context Injection:")
    if stats.total_injections > 0:
        tc = stats
        lines.append(
            f"  Token counts: min={tc.token_min}, median={tc.token_median}, "
            f"p95={tc.token_p95}, max={tc.token_max}"
        )
        exceedance_pct = (
            stats.total_threshold_exceedances / stats.total_injections * 100
            if stats.total_injections > 0
            else 0
        )
        total_exceed = stats.total_threshold_exceedances
        lines.append(f"  Threshold exceedances: {total_exceed} ({exceedance_pct:.1f}%)")
    else:
        lines.append("  No injections recorded")

    # Find token recommendation
    token_recs = [r for r in report.recommendations if "token" in r.parameter.lower()]
    for rec in token_recs:
        if rec.recommended_value is not None:
            lines.append(f"  -> RECOMMENDATION: {rec.reason}")
        else:
            lines.append(f"  -> {rec.reason}")
    lines.append("")

    # Performance
    lines.append("Performance:")
    parsing_status = (
        "pass" if report.performance_status.get("parsing_p95_under_200ms", True) else "FAIL"
    )
    injection_status = (
        "pass" if report.performance_status.get("injection_p95_under_50ms", True) else "FAIL"
    )

    if stats.parsing_p95_ms > 0:
        pmed, pp95 = stats.parsing_median_ms, stats.parsing_p95_ms
        lines.append(
            f"  Parsing: median={pmed}ms, p95={pp95}ms (target: <200ms) [{parsing_status}]"
        )
    else:
        lines.append("  Parsing: No data")

    if stats.injection_p95_ms > 0:
        imed, ip95 = stats.injection_median_ms, stats.injection_p95_ms
        lines.append(
            f"  Injection: median={imed}ms, p95={ip95}ms (target: <50ms) [{injection_status}]"
        )
    else:
        lines.append("  Injection: No data")

    if report.performance_status.get(
        "parsing_p95_under_200ms", True
    ) and report.performance_status.get("injection_p95_under_50ms", True):
        lines.append("  -> RECOMMENDATION: Performance meets targets")
    else:
        lines.append(
            "  -> RECOMMENDATION: Performance issues detected, investigate slow operations"
        )
    lines.append("")

    # Warnings
    lines.append("Warnings:")
    if stats.total_warnings > 0:
        # Sort by count descending
        sorted_warnings = sorted(stats.warnings_by_type.items(), key=lambda x: x[1], reverse=True)
        most_common = ", ".join(f"{w[0]} ({w[1]})" for w in sorted_warnings[:3])
        lines.append(f"  Most common: {most_common}")

        if stats.files_with_most_warnings:
            files_str = ", ".join(
                f"{Path(f['file']).name} ({f['warning_count']})"
                for f in stats.files_with_most_warnings[:3]
            )
            lines.append(f"  Files with most warnings: {files_str}")

        # Check for refactoring suggestions
        highest_file = stats.files_with_most_warnings[0] if stats.files_with_most_warnings else None
        if highest_file and highest_file["warning_count"] > 10:
            file_name = Path(highest_file["file"]).name
            lines.append(f"  -> RECOMMENDATION: Review {file_name} for refactoring opportunities")
    else:
        lines.append("  No warnings recorded")
    lines.append("")

    # Relationship Graph
    lines.append("Relationship Graph:")
    lines.append(f"  Average files tracked: {stats.avg_total_files:.0f}")
    lines.append(f"  Average relationships: {stats.avg_total_relationships:.0f}")
    lines.append("")

    # Function Usage Distribution
    total_functions = (
        stats.total_functions_1_to_3 + stats.total_functions_4_to_10 + stats.total_functions_11_plus
    )
    if total_functions > 0:
        lines.append("Function Usage Distribution:")
        f1_3, f4_10, f11 = (
            stats.total_functions_1_to_3,
            stats.total_functions_4_to_10,
            stats.total_functions_11_plus,
        )
        lines.append(f"  1-3 files: {f1_3} ({f1_3/total_functions:.0%})")
        lines.append(f"  4-10 files: {f4_10} ({f4_10/total_functions:.0%})")
        lines.append(f"  11+ files: {f11} ({f11/total_functions:.0%})")

        usage_recs = [r for r in report.recommendations if "threshold" in r.parameter.lower()]
        for rec in usage_recs:
            if rec.recommended_value is not None:
                lines.append(f"  -> RECOMMENDATION: {rec.reason}")
            else:
                lines.append(f"  -> {rec.reason}")
        lines.append("")

    # Re-read Patterns
    if stats.files_with_re_reads:
        lines.append("Re-read Patterns:")
        for pattern in stats.files_with_re_reads[:5]:
            file_name = Path(pattern["file"]).name if "/" in pattern["file"] else pattern["file"]
            lines.append(f"  {file_name}: {pattern['read_count']} reads")
        lines.append("")

    # Outliers
    if report.outliers:
        lines.append("Outliers Detected:")
        for outlier in report.outliers[:10]:
            lines.append(f"  - {outlier}")
        lines.append("")

    return "\n".join(lines)


def analyze_metrics(file_paths: List[Path]) -> AnalysisReport:
    """Analyze metrics from one or more JSONL files.

    Args:
        file_paths: List of paths to session_metrics.jsonl files.

    Returns:
        Complete analysis report.
    """
    # Collect all sessions from all files
    all_sessions: List[Dict[str, Any]] = []

    for file_path in file_paths:
        try:
            sessions = parse_session_metrics(file_path)
            all_sessions.extend(sessions)
        except FileNotFoundError as e:
            print(f"Warning: {e}", file=sys.stderr)
            continue

    if not all_sessions:
        return AnalysisReport(
            sessions_analyzed=0,
            date_range=("", ""),
            statistics=AggregateStatistics(),
            recommendations=[],
            outliers=[],
            performance_status={},
        )

    # Sort by start time
    all_sessions.sort(key=lambda x: x.get("start_time", ""))

    # Get date range
    date_range = (
        all_sessions[0].get("start_time", ""),
        all_sessions[-1].get("end_time", ""),
    )

    # Compute statistics
    stats = compute_aggregate_statistics(all_sessions)

    # Generate recommendations
    recommendations = generate_recommendations(all_sessions, stats)

    # Identify outliers
    outliers = identify_outliers(all_sessions, stats)

    # Check performance targets
    performance_status = check_performance_targets(stats)

    return AnalysisReport(
        sessions_analyzed=len(all_sessions),
        date_range=date_range,
        statistics=stats,
        recommendations=recommendations,
        outliers=outliers,
        performance_status=performance_status,
    )


def main() -> int:
    """Main entry point for the metrics analysis tool.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = argparse.ArgumentParser(
        description="Analyze cross-file context session metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python analyze_metrics.py .cross_file_context_logs/session_metrics.jsonl
    python analyze_metrics.py metrics1.jsonl metrics2.jsonl
        """,
    )
    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="Path(s) to session_metrics.jsonl file(s)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON instead of human-readable text",
    )

    args = parser.parse_args()

    try:
        report = analyze_metrics(args.files)

        if report.sessions_analyzed == 0:
            print("No valid session metrics found in the provided files.", file=sys.stderr)
            return 1

        if args.json:
            # JSON output
            output = {
                "sessions_analyzed": report.sessions_analyzed,
                "date_range": {"start": report.date_range[0], "end": report.date_range[1]},
                "statistics": {
                    "cache_performance": {
                        "avg_hit_rate": report.statistics.avg_hit_rate,
                        "avg_peak_size_kb": report.statistics.avg_peak_size_kb,
                        "total_evictions_lru": report.statistics.total_evictions_lru,
                    },
                    "context_injection": {
                        "total_injections": report.statistics.total_injections,
                        "token_min": report.statistics.token_min,
                        "token_median": report.statistics.token_median,
                        "token_p95": report.statistics.token_p95,
                        "token_max": report.statistics.token_max,
                        "threshold_exceedances": report.statistics.total_threshold_exceedances,
                    },
                    "performance": {
                        "parsing_median_ms": report.statistics.parsing_median_ms,
                        "parsing_p95_ms": report.statistics.parsing_p95_ms,
                        "injection_median_ms": report.statistics.injection_median_ms,
                        "injection_p95_ms": report.statistics.injection_p95_ms,
                    },
                    "warnings": {
                        "total": report.statistics.total_warnings,
                        "by_type": report.statistics.warnings_by_type,
                    },
                },
                "recommendations": [
                    {
                        "parameter": r.parameter,
                        "current_value": r.current_value,
                        "recommended_value": r.recommended_value,
                        "reason": r.reason,
                        "confidence": r.confidence,
                    }
                    for r in report.recommendations
                ],
                "outliers": report.outliers,
                "performance_status": report.performance_status,
            }
            print(json.dumps(output, indent=2))
        else:
            # Human-readable output
            print(format_report(report))

        return 0

    except Exception as e:
        print(f"Error analyzing metrics: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
