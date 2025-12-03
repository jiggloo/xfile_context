# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Unit tests for Query API (TDD Section 3.10.4).

Tests the QueryAPI class which provides programmatic access to system state:
- get_recent_injections(target_file, limit)
- get_relationship_graph()
- get_dependents(file_path)
- get_dependencies(file_path)
- get_session_metrics()
- get_cache_statistics()

Related Requirements:
- FR-29 (query API for injection events)
- FR-18 (impact analysis)
- FR-23 (graph export)
- T-5.5 (API retrieves recent injection events)
"""

import json
import tempfile
from pathlib import Path
from typing import Dict

import pytest

from xfile_context.cache import WorkingMemoryCache
from xfile_context.config import Config
from xfile_context.injection_logger import InjectionEvent, InjectionLogger
from xfile_context.metrics_collector import MetricsCollector
from xfile_context.models import Relationship, RelationshipGraph, RelationshipType
from xfile_context.query_api import QueryAPI
from xfile_context.warning_logger import WarningLogger


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_graph():
    """Create a sample RelationshipGraph with test data."""
    graph = RelationshipGraph()

    # Add some test relationships
    rel1 = Relationship(
        source_file="/project/src/main.py",
        target_file="/project/src/utils.py",
        relationship_type=RelationshipType.IMPORT,
        line_number=5,
        target_symbol="helper_func",
        target_line=10,
    )
    rel2 = Relationship(
        source_file="/project/src/main.py",
        target_file="/project/src/config.py",
        relationship_type=RelationshipType.IMPORT,
        line_number=6,
        target_symbol="Config",
        target_line=1,
    )
    rel3 = Relationship(
        source_file="/project/src/service.py",
        target_file="/project/src/utils.py",
        relationship_type=RelationshipType.FUNCTION_CALL,
        line_number=20,
        target_symbol="helper_func",
        target_line=10,
    )

    graph.add_relationship(rel1)
    graph.add_relationship(rel2)
    graph.add_relationship(rel3)

    return graph


@pytest.fixture
def sample_cache(temp_dir):
    """Create a sample WorkingMemoryCache."""
    file_event_timestamps: Dict[str, float] = {}
    cache = WorkingMemoryCache(
        file_event_timestamps=file_event_timestamps,
        size_limit_kb=50,
    )
    return cache


@pytest.fixture
def sample_injection_logger(temp_dir):
    """Create a sample InjectionLogger with test data."""
    log_dir = temp_dir / ".cross_file_context_logs"
    logger = InjectionLogger(log_dir=log_dir)

    # Log some test injection events
    event1 = InjectionEvent.create(
        source_file="/project/src/utils.py",
        target_file="/project/src/main.py",
        relationship_type="import",
        snippet="def helper_func():\n    pass",
        snippet_location="utils.py:10-15",
        cache_age_seconds=120.0,
        cache_hit=True,
        token_count=10,
        context_token_total=10,
    )
    event2 = InjectionEvent.create(
        source_file="/project/src/config.py",
        target_file="/project/src/main.py",
        relationship_type="import",
        snippet="class Config:\n    pass",
        snippet_location="config.py:1-5",
        cache_age_seconds=None,
        cache_hit=False,
        token_count=8,
        context_token_total=18,
    )

    logger.log_injection(event1)
    logger.log_injection(event2)

    # Return the same logger (don't close and reopen, which clears statistics)
    return logger


@pytest.fixture
def sample_metrics_collector(temp_dir):
    """Create a sample MetricsCollector."""
    log_dir = temp_dir / ".cross_file_context_logs"
    collector = MetricsCollector(log_dir=log_dir)
    collector.record_injection_token_count(100)
    collector.record_injection_token_count(150)
    collector.record_parsing_time_ms(45)
    return collector


@pytest.fixture
def sample_warning_logger(temp_dir):
    """Create a sample WarningLogger."""
    log_dir = temp_dir / ".cross_file_context_logs"
    return WarningLogger(log_dir=log_dir)


@pytest.fixture
def query_api(
    sample_graph,
    sample_cache,
    sample_injection_logger,
    sample_metrics_collector,
    sample_warning_logger,
):
    """Create a QueryAPI instance with test components."""
    return QueryAPI(
        graph=sample_graph,
        cache=sample_cache,
        injection_logger=sample_injection_logger,
        metrics_collector=sample_metrics_collector,
        warning_logger=sample_warning_logger,
        project_root="/project",
    )


class TestQueryAPIGetRecentInjections:
    """Tests for get_recent_injections() method (FR-29, T-5.5)."""

    def test_get_recent_injections_returns_list(self, query_api):
        """get_recent_injections() should return a list of dictionaries."""
        result = query_api.get_recent_injections()
        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)

    def test_get_recent_injections_returns_events(self, query_api):
        """get_recent_injections() should return injection event data."""
        result = query_api.get_recent_injections()
        assert len(result) == 2

        # Check first event (most recent is first)
        event = result[0]
        assert event["event_type"] == "context_injection"
        assert "timestamp" in event
        assert "source_file" in event
        assert "target_file" in event
        assert "relationship_type" in event
        assert "snippet" in event
        assert "token_count" in event

    def test_get_recent_injections_filters_by_target_file(self, query_api):
        """get_recent_injections() should filter by target_file when provided."""
        result = query_api.get_recent_injections(target_file="/project/src/main.py", limit=10)
        assert len(result) == 2

        for event in result:
            assert event["target_file"] == "/project/src/main.py"

    def test_get_recent_injections_respects_limit(self, query_api):
        """get_recent_injections() should respect the limit parameter."""
        result = query_api.get_recent_injections(limit=1)
        assert len(result) == 1

    def test_get_recent_injections_empty_log(self, temp_dir):
        """get_recent_injections() should return empty list for empty log."""
        log_dir = temp_dir / "empty_logs"
        empty_logger = InjectionLogger(log_dir=log_dir)

        api = QueryAPI(
            graph=RelationshipGraph(),
            cache=WorkingMemoryCache(file_event_timestamps={}, size_limit_kb=50),
            injection_logger=empty_logger,
            metrics_collector=MetricsCollector(log_dir=log_dir),
            warning_logger=WarningLogger(log_dir=log_dir),
        )

        result = api.get_recent_injections()
        assert result == []


class TestQueryAPIGetRelationshipGraph:
    """Tests for get_relationship_graph() method (FR-23)."""

    def test_get_relationship_graph_returns_dict(self, query_api):
        """get_relationship_graph() should return a dictionary."""
        result = query_api.get_relationship_graph()
        assert isinstance(result, dict)

    def test_get_relationship_graph_has_required_sections(self, query_api):
        """get_relationship_graph() should have all required sections."""
        result = query_api.get_relationship_graph()

        assert "metadata" in result
        assert "files" in result
        assert "relationships" in result
        assert "graph_metadata" in result

    def test_get_relationship_graph_metadata(self, query_api):
        """get_relationship_graph() metadata should have required fields."""
        result = query_api.get_relationship_graph()
        metadata = result["metadata"]

        assert "timestamp" in metadata
        assert "version" in metadata
        assert "language" in metadata
        assert metadata["language"] == "python"
        assert "total_files" in metadata
        assert "total_relationships" in metadata

    def test_get_relationship_graph_includes_project_root(self, query_api):
        """get_relationship_graph() should include project_root when set."""
        result = query_api.get_relationship_graph()
        assert result["metadata"]["project_root"] == "/project"

    def test_get_relationship_graph_relationships(self, query_api):
        """get_relationship_graph() should include all relationships."""
        result = query_api.get_relationship_graph()
        relationships = result["relationships"]

        assert len(relationships) == 3
        for rel in relationships:
            assert "source_file" in rel
            assert "target_file" in rel
            assert "relationship_type" in rel
            assert "line_number" in rel

    def test_get_relationship_graph_is_json_serializable(self, query_api):
        """get_relationship_graph() result should be JSON serializable."""
        result = query_api.get_relationship_graph()
        # Should not raise
        json_str = json.dumps(result)
        assert isinstance(json_str, str)


class TestQueryAPIGetDependents:
    """Tests for get_dependents() method (FR-18)."""

    def test_get_dependents_returns_list(self, query_api):
        """get_dependents() should return a list."""
        result = query_api.get_dependents("/project/src/utils.py")
        assert isinstance(result, list)

    def test_get_dependents_finds_dependent_files(self, query_api):
        """get_dependents() should find files that depend on the target."""
        result = query_api.get_dependents("/project/src/utils.py")

        assert len(result) == 2

        source_files = {rel["source_file"] for rel in result}
        assert "/project/src/main.py" in source_files
        assert "/project/src/service.py" in source_files

    def test_get_dependents_returns_relationship_details(self, query_api):
        """get_dependents() should return full relationship details."""
        result = query_api.get_dependents("/project/src/utils.py")

        for rel in result:
            assert "source_file" in rel
            assert "target_file" in rel
            assert rel["target_file"] == "/project/src/utils.py"
            assert "relationship_type" in rel
            assert "line_number" in rel

    def test_get_dependents_empty_for_unknown_file(self, query_api):
        """get_dependents() should return empty list for unknown file."""
        result = query_api.get_dependents("/project/src/unknown.py")
        assert result == []


class TestQueryAPIGetDependencies:
    """Tests for get_dependencies() method."""

    def test_get_dependencies_returns_list(self, query_api):
        """get_dependencies() should return a list."""
        result = query_api.get_dependencies("/project/src/main.py")
        assert isinstance(result, list)

    def test_get_dependencies_finds_dependencies(self, query_api):
        """get_dependencies() should find files the target depends on."""
        result = query_api.get_dependencies("/project/src/main.py")

        assert len(result) == 2

        target_files = {rel["target_file"] for rel in result}
        assert "/project/src/utils.py" in target_files
        assert "/project/src/config.py" in target_files

    def test_get_dependencies_returns_relationship_details(self, query_api):
        """get_dependencies() should return full relationship details."""
        result = query_api.get_dependencies("/project/src/main.py")

        for rel in result:
            assert "source_file" in rel
            assert rel["source_file"] == "/project/src/main.py"
            assert "target_file" in rel
            assert "relationship_type" in rel
            assert "line_number" in rel

    def test_get_dependencies_empty_for_file_with_no_dependencies(self, query_api):
        """get_dependencies() should return empty list for file with no deps."""
        result = query_api.get_dependencies("/project/src/utils.py")
        assert result == []


class TestQueryAPIGetSessionMetrics:
    """Tests for get_session_metrics() method."""

    def test_get_session_metrics_returns_dict(self, query_api):
        """get_session_metrics() should return a dictionary."""
        result = query_api.get_session_metrics()
        assert isinstance(result, dict)

    def test_get_session_metrics_has_session_info(self, query_api):
        """get_session_metrics() should have session info."""
        result = query_api.get_session_metrics()

        assert "session_id" in result
        assert "start_time" in result
        assert "end_time" in result

    def test_get_session_metrics_has_cache_performance(self, query_api):
        """get_session_metrics() should have cache performance metrics."""
        result = query_api.get_session_metrics()

        assert "cache_performance" in result
        cache = result["cache_performance"]
        assert "hit_rate" in cache
        assert "miss_rate" in cache

    def test_get_session_metrics_has_context_injection(self, query_api):
        """get_session_metrics() should have context injection metrics."""
        result = query_api.get_session_metrics()

        assert "context_injection" in result
        injection = result["context_injection"]
        assert "total_injections" in injection
        assert "token_counts" in injection

    def test_get_session_metrics_has_relationship_graph(self, query_api):
        """get_session_metrics() should have relationship graph metrics."""
        result = query_api.get_session_metrics()

        assert "relationship_graph" in result
        graph = result["relationship_graph"]
        assert "total_files" in graph
        assert "total_relationships" in graph

    def test_get_session_metrics_is_json_serializable(self, query_api):
        """get_session_metrics() result should be JSON serializable."""
        result = query_api.get_session_metrics()
        json_str = json.dumps(result)
        assert isinstance(json_str, str)


class TestQueryAPIGetCacheStatistics:
    """Tests for get_cache_statistics() method."""

    def test_get_cache_statistics_returns_dict(self, query_api):
        """get_cache_statistics() should return a dictionary."""
        result = query_api.get_cache_statistics()
        assert isinstance(result, dict)

    def test_get_cache_statistics_has_basic_metrics(self, query_api):
        """get_cache_statistics() should have basic cache metrics."""
        result = query_api.get_cache_statistics()

        assert "hits" in result
        assert "misses" in result
        assert "staleness_refreshes" in result
        assert "evictions_lru" in result

    def test_get_cache_statistics_has_size_metrics(self, query_api):
        """get_cache_statistics() should have size metrics."""
        result = query_api.get_cache_statistics()

        assert "current_size_bytes" in result
        assert "peak_size_bytes" in result
        assert "current_entry_count" in result
        assert "peak_entry_count" in result

    def test_get_cache_statistics_has_hit_rate(self, query_api):
        """get_cache_statistics() should include calculated hit rate."""
        result = query_api.get_cache_statistics()
        assert "hit_rate" in result
        assert isinstance(result["hit_rate"], float)


class TestQueryAPIGetInjectionStatistics:
    """Tests for get_injection_statistics() method."""

    def test_get_injection_statistics_returns_dict(self, query_api):
        """get_injection_statistics() should return a dictionary."""
        result = query_api.get_injection_statistics()
        assert isinstance(result, dict)

    def test_get_injection_statistics_has_totals(self, query_api):
        """get_injection_statistics() should have total injection count."""
        result = query_api.get_injection_statistics()

        assert "total_injections" in result
        assert result["total_injections"] == 2

    def test_get_injection_statistics_has_breakdown(self, query_api):
        """get_injection_statistics() should have breakdown by type."""
        result = query_api.get_injection_statistics()

        assert "by_relationship_type" in result
        assert "by_source_file" in result

    def test_get_injection_statistics_has_cache_info(self, query_api):
        """get_injection_statistics() should have cache hit/miss info."""
        result = query_api.get_injection_statistics()

        assert "cache_hit_count" in result
        assert "cache_miss_count" in result
        assert "cache_hit_rate" in result


class TestQueryAPIGetWarningStatistics:
    """Tests for get_warning_statistics() method."""

    def test_get_warning_statistics_returns_dict(self, query_api):
        """get_warning_statistics() should return a dictionary."""
        result = query_api.get_warning_statistics()
        assert isinstance(result, dict)

    def test_get_warning_statistics_has_totals(self, query_api):
        """get_warning_statistics() should have total warning count."""
        result = query_api.get_warning_statistics()
        assert "total_warnings" in result

    def test_get_warning_statistics_has_breakdown(self, query_api):
        """get_warning_statistics() should have breakdown by type."""
        result = query_api.get_warning_statistics()
        assert "by_type" in result


class TestQueryAPIGetGraphStatistics:
    """Tests for get_graph_statistics() method."""

    def test_get_graph_statistics_returns_dict(self, query_api):
        """get_graph_statistics() should return a dictionary."""
        result = query_api.get_graph_statistics()
        assert isinstance(result, dict)

    def test_get_graph_statistics_has_counts(self, query_api):
        """get_graph_statistics() should have file and relationship counts."""
        result = query_api.get_graph_statistics()

        assert "total_files" in result
        assert "total_relationships" in result
        assert result["total_relationships"] == 3

    def test_get_graph_statistics_has_most_connected(self, query_api):
        """get_graph_statistics() should have most connected files."""
        result = query_api.get_graph_statistics()
        assert "most_connected_files" in result
        assert isinstance(result["most_connected_files"], list)


class TestQueryAPIFromService:
    """Tests for QueryAPI.from_service() class method."""

    def test_from_service_creates_query_api(self, temp_dir):
        """from_service() should create a QueryAPI from a service."""
        from xfile_context.service import CrossFileContextService

        config = Config()
        service = CrossFileContextService(
            config=config,
            project_root=str(temp_dir),
        )

        api = QueryAPI.from_service(service)

        assert isinstance(api, QueryAPI)
        assert api._graph is service._graph
        assert api._cache is service.cache
        assert api._project_root == str(temp_dir)

        # Cleanup
        service.shutdown()

    def test_from_service_api_methods_work(self, temp_dir):
        """API created from service should have working methods."""
        from xfile_context.service import CrossFileContextService

        config = Config()
        service = CrossFileContextService(
            config=config,
            project_root=str(temp_dir),
        )

        api = QueryAPI.from_service(service)

        # These should not raise
        graph = api.get_relationship_graph()
        assert isinstance(graph, dict)

        cache_stats = api.get_cache_statistics()
        assert isinstance(cache_stats, dict)

        # Cleanup
        service.shutdown()


class TestQueryAPIJSONCompatibility:
    """Tests to ensure all API returns are JSON-compatible."""

    def test_all_methods_return_json_compatible(self, query_api):
        """All API methods should return JSON-serializable data."""
        # Test each method
        methods_to_test = [
            ("get_recent_injections", {}),
            ("get_relationship_graph", {}),
            ("get_dependents", {"file_path": "/project/src/utils.py"}),
            ("get_dependencies", {"file_path": "/project/src/main.py"}),
            ("get_session_metrics", {}),
            ("get_cache_statistics", {}),
            ("get_injection_statistics", {}),
            ("get_warning_statistics", {}),
            ("get_graph_statistics", {}),
        ]

        for method_name, kwargs in methods_to_test:
            method = getattr(query_api, method_name)
            result = method(**kwargs)

            # Should be JSON serializable
            try:
                json_str = json.dumps(result)
                assert isinstance(json_str, str)
            except (TypeError, ValueError) as e:
                pytest.fail(f"{method_name}() returned non-JSON data: {e}")
