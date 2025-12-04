# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Benchmark script for comparing direct vs two-phase analysis performance.

This script measures and compares the performance of:
1. Direct analysis mode (AST -> Relationships via detect())
2. Two-phase analysis mode (AST -> FileSymbolData -> Relationships)

Usage:
    python scripts/benchmark_analysis.py [--iterations N] [--directory PATH]

Output:
    - Timing statistics for both modes
    - Memory usage comparison
    - Relationship count verification (both should produce same results)
"""

import argparse
import gc
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from xfile_context.analyzers.python_analyzer import PythonAnalyzer
from xfile_context.detectors import (
    ClassInheritanceDetector,
    ConditionalImportDetector,
    DecoratorDetector,
    DetectorRegistry,
    DynamicDispatchDetector,
    ExecEvalDetector,
    FunctionCallDetector,
    ImportDetector,
    MetaclassDetector,
    MonkeyPatchingDetector,
    WildcardImportDetector,
)
from xfile_context.models import RelationshipGraph
from xfile_context.relationship_builder import RelationshipBuilder


def create_analyzer() -> Tuple[PythonAnalyzer, RelationshipGraph]:
    """Create a fresh analyzer with all detectors registered."""
    graph = RelationshipGraph()
    registry = DetectorRegistry()

    # Register all detectors
    registry.register(ImportDetector())
    registry.register(ConditionalImportDetector())
    registry.register(WildcardImportDetector())
    registry.register(FunctionCallDetector())
    registry.register(ClassInheritanceDetector())

    # Dynamic pattern detectors
    project_root = str(Path.cwd())
    registry.register(DynamicDispatchDetector(project_root))
    registry.register(MonkeyPatchingDetector(project_root))
    registry.register(ExecEvalDetector(project_root))
    registry.register(DecoratorDetector(project_root))
    registry.register(MetaclassDetector(project_root))

    analyzer = PythonAnalyzer(graph=graph, detector_registry=registry)
    return analyzer, graph


def collect_python_files(directory: Path, max_files: int = 100) -> List[str]:
    """Collect Python files from directory."""
    files = []
    for py_file in directory.rglob("*.py"):
        # Skip test files and __pycache__
        if "__pycache__" in str(py_file) or "test_" in py_file.name:
            continue
        files.append(str(py_file))
        if len(files) >= max_files:
            break
    return files


def benchmark_direct_analysis(files: List[str], iterations: int = 3) -> Dict[str, Any]:
    """Benchmark direct analysis mode."""
    times: List[float] = []
    memory_peaks: List[int] = []
    relationship_counts: List[int] = []

    for i in range(iterations):
        # Force garbage collection
        gc.collect()

        # Start memory tracking
        tracemalloc.start()

        # Create fresh analyzer
        analyzer, graph = create_analyzer()

        # Time the analysis
        start_time = time.perf_counter()

        success = 0
        for filepath in files:
            if analyzer.analyze_file(filepath):
                success += 1

        end_time = time.perf_counter()

        # Get memory stats
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        times.append(end_time - start_time)
        memory_peaks.append(peak)
        relationship_counts.append(len(graph.get_all_relationships()))

        print(
            f"  Direct iteration {i + 1}: {times[-1]:.3f}s, "
            f"{memory_peaks[-1] / 1024 / 1024:.2f}MB peak, "
            f"{relationship_counts[-1]} relationships"
        )

    return {
        "mode": "direct",
        "times": times,
        "mean_time": statistics.mean(times),
        "std_time": statistics.stdev(times) if len(times) > 1 else 0,
        "memory_peaks": memory_peaks,
        "mean_memory_mb": statistics.mean(memory_peaks) / 1024 / 1024,
        "relationship_counts": relationship_counts,
    }


def benchmark_two_phase_analysis(files: List[str], iterations: int = 3) -> Dict[str, Any]:
    """Benchmark two-phase analysis mode."""
    times: List[float] = []
    phase1_times: List[float] = []
    phase2_times: List[float] = []
    memory_peaks: List[int] = []
    relationship_counts: List[int] = []

    for i in range(iterations):
        # Force garbage collection
        gc.collect()

        # Start memory tracking
        tracemalloc.start()

        # Create fresh analyzer
        analyzer, graph = create_analyzer()
        builder = RelationshipBuilder()

        # Time Phase 1: Symbol extraction
        start_time = time.perf_counter()
        phase1_start = start_time

        for filepath in files:
            symbol_data = analyzer.extract_file_symbols(filepath)
            if symbol_data and symbol_data.is_valid:
                builder.add_file_data(symbol_data)

        phase1_end = time.perf_counter()
        phase1_times.append(phase1_end - phase1_start)

        # Time Phase 2: Relationship building
        phase2_start = time.perf_counter()

        relationships = builder.build_relationships()
        for rel in relationships:
            graph.add_relationship(rel)

        phase2_end = time.perf_counter()
        phase2_times.append(phase2_end - phase2_start)

        end_time = phase2_end

        # Get memory stats
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        total_time = end_time - start_time
        times.append(total_time)
        memory_peaks.append(peak)
        relationship_counts.append(len(graph.get_all_relationships()))

        print(
            f"  Two-phase iteration {i + 1}: {times[-1]:.3f}s "
            f"(P1: {phase1_times[-1]:.3f}s, P2: {phase2_times[-1]:.3f}s), "
            f"{memory_peaks[-1] / 1024 / 1024:.2f}MB peak, "
            f"{relationship_counts[-1]} relationships"
        )

    return {
        "mode": "two-phase",
        "times": times,
        "mean_time": statistics.mean(times),
        "std_time": statistics.stdev(times) if len(times) > 1 else 0,
        "phase1_times": phase1_times,
        "mean_phase1_time": statistics.mean(phase1_times),
        "phase2_times": phase2_times,
        "mean_phase2_time": statistics.mean(phase2_times),
        "memory_peaks": memory_peaks,
        "mean_memory_mb": statistics.mean(memory_peaks) / 1024 / 1024,
        "relationship_counts": relationship_counts,
    }


def benchmark_incremental_analysis(files: List[str], iterations: int = 3) -> Dict[str, Any]:
    """Benchmark incremental two-phase analysis with caching."""
    from xfile_context.symbol_cache import SymbolDataCache

    times: List[float] = []
    cache_hit_rates: List[float] = []
    relationship_counts: List[int] = []

    # First run populates the cache
    cache = SymbolDataCache(max_entries=1000)
    analyzer, graph = create_analyzer()
    builder = RelationshipBuilder()

    # Initial run (no cache hits)
    start_time = time.perf_counter()
    for filepath in files:
        symbol_data = analyzer.extract_file_symbols(filepath)
        if symbol_data and symbol_data.is_valid:
            cache.set(filepath, symbol_data)
            builder.add_file_data(symbol_data)
    relationships = builder.build_relationships()
    for rel in relationships:
        graph.add_relationship(rel)
    initial_time = time.perf_counter() - start_time
    print(f"  Initial run (populating cache): {initial_time:.3f}s")

    # Subsequent runs use cache
    for i in range(iterations):
        gc.collect()

        # Create fresh graph but reuse cache
        analyzer, graph = create_analyzer()
        builder = RelationshipBuilder()

        start_time = time.perf_counter()

        for filepath in files:
            # Try cache first
            if cache.is_valid(filepath):
                symbol_data = cache.get(filepath)
            else:
                symbol_data = analyzer.extract_file_symbols(filepath)
                if symbol_data and symbol_data.is_valid:
                    cache.set(filepath, symbol_data)

            if symbol_data and symbol_data.is_valid:
                builder.add_file_data(symbol_data)

        relationships = builder.build_relationships()
        for rel in relationships:
            graph.add_relationship(rel)

        end_time = time.perf_counter()

        stats = cache.get_statistics()
        times.append(end_time - start_time)
        cache_hit_rates.append(stats["hit_rate"])
        relationship_counts.append(len(graph.get_all_relationships()))

        print(
            f"  Incremental iteration {i + 1}: {times[-1]:.3f}s, "
            f"cache hit rate: {cache_hit_rates[-1]:.1%}, "
            f"{relationship_counts[-1]} relationships"
        )

    return {
        "mode": "incremental",
        "times": times,
        "mean_time": statistics.mean(times),
        "std_time": statistics.stdev(times) if len(times) > 1 else 0,
        "cache_hit_rates": cache_hit_rates,
        "mean_cache_hit_rate": statistics.mean(cache_hit_rates),
        "relationship_counts": relationship_counts,
    }


def print_results(
    direct: Dict[str, Any],
    two_phase: Dict[str, Any],
    incremental: Optional[Dict[str, Any]] = None,
) -> None:
    """Print benchmark comparison results."""
    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)

    print("\nDirect Analysis:")
    print(f"  Mean time: {direct['mean_time']:.3f}s (± {direct['std_time']:.3f}s)")
    print(f"  Mean memory: {direct['mean_memory_mb']:.2f} MB")
    print(f"  Relationships: {direct['relationship_counts'][-1]}")

    print("\nTwo-Phase Analysis (no cache):")
    print(f"  Mean time: {two_phase['mean_time']:.3f}s (± {two_phase['std_time']:.3f}s)")
    print(f"  - Phase 1 (symbol extraction): {two_phase['mean_phase1_time']:.3f}s")
    print(f"  - Phase 2 (relationship building): {two_phase['mean_phase2_time']:.3f}s")
    print(f"  Mean memory: {two_phase['mean_memory_mb']:.2f} MB")
    print(f"  Relationships: {two_phase['relationship_counts'][-1]}")

    if incremental:
        print("\nIncremental Analysis (with cache):")
        print(f"  Mean time: {incremental['mean_time']:.3f}s (± {incremental['std_time']:.3f}s)")
        print(f"  Cache hit rate: {incremental['mean_cache_hit_rate']:.1%}")
        print(f"  Relationships: {incremental['relationship_counts'][-1]}")

    # Calculate comparison
    time_diff = two_phase["mean_time"] - direct["mean_time"]
    time_ratio = two_phase["mean_time"] / direct["mean_time"] if direct["mean_time"] > 0 else 0
    memory_diff = two_phase["mean_memory_mb"] - direct["mean_memory_mb"]

    print("\nComparison (Two-Phase vs Direct):")
    print(f"  Time difference: {time_diff:+.3f}s ({time_ratio:.2f}x)")
    print(f"  Memory difference: {memory_diff:+.2f} MB")

    if time_ratio <= 1.0:
        print("  ✅ Two-phase is faster or equal")
    elif time_ratio <= 1.2:
        print("  ⚠️ Two-phase is slightly slower (within 20%)")
    else:
        print("  ❌ Two-phase is significantly slower")

    if incremental:
        incr_ratio = (
            incremental["mean_time"] / direct["mean_time"] if direct["mean_time"] > 0 else 0
        )
        speedup = (
            two_phase["mean_time"] / incremental["mean_time"] if incremental["mean_time"] > 0 else 0
        )
        print("\nIncremental Analysis Benefits:")
        print(f"  vs Direct: {incr_ratio:.2f}x")
        print(f"  Speedup from caching: {speedup:.1f}x faster than uncached two-phase")


def main() -> None:
    """Run the benchmark."""
    parser = argparse.ArgumentParser(description="Benchmark analysis modes")
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=3,
        help="Number of iterations per benchmark (default: 3)",
    )
    parser.add_argument(
        "--directory",
        "-d",
        type=str,
        default="src/xfile_context",
        help="Directory to analyze (default: src/xfile_context)",
    )
    parser.add_argument(
        "--max-files",
        "-m",
        type=int,
        default=50,
        help="Maximum number of files to analyze (default: 50)",
    )
    parser.add_argument(
        "--skip-incremental", action="store_true", help="Skip incremental analysis benchmark"
    )
    args = parser.parse_args()

    directory = Path(args.directory)
    if not directory.exists():
        print(f"Error: Directory not found: {directory}")
        sys.exit(1)

    print(f"Collecting Python files from {directory}...")
    files = collect_python_files(directory, args.max_files)
    print(f"Found {len(files)} Python files")

    if not files:
        print("No Python files found!")
        sys.exit(1)

    print(f"\nRunning benchmarks with {args.iterations} iterations each...\n")

    print("Direct Analysis Mode:")
    direct_results = benchmark_direct_analysis(files, args.iterations)

    print("\nTwo-Phase Analysis Mode (no cache):")
    two_phase_results = benchmark_two_phase_analysis(files, args.iterations)

    incremental_results = None
    if not args.skip_incremental:
        print("\nIncremental Analysis Mode (with cache):")
        incremental_results = benchmark_incremental_analysis(files, args.iterations)

    print_results(direct_results, two_phase_results, incremental_results)


if __name__ == "__main__":
    main()
