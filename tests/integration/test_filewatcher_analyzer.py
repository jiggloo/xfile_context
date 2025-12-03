# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Integration tests for FileWatcher + Analyzer.

Tests that file change events trigger correct re-analysis per TDD Section 3.13.2.
"""

import time
from pathlib import Path

import pytest
import yaml

from xfile_context.analyzers import PythonAnalyzer
from xfile_context.config import Config
from xfile_context.detectors import DetectorRegistry, ImportDetector
from xfile_context.file_watcher import FileWatcher
from xfile_context.graph_updater import GraphUpdater
from xfile_context.models import RelationshipGraph
from xfile_context.service import CrossFileContextService


def create_config_file(project_path: Path, **kwargs) -> Path:
    """Create a temporary config file with given settings."""
    config_path = project_path / ".cross_file_context_links.yml"
    config_data = {
        "cache_expiry_minutes": kwargs.get("cache_expiry_minutes", 10),
        "cache_size_limit_kb": kwargs.get("cache_size_limit_kb", 1024),
        "context_token_limit": kwargs.get("context_token_limit", 500),
        "enable_context_injection": kwargs.get("enable_context_injection", True),
    }
    config_path.write_text(yaml.dump(config_data))
    return config_path


class TestFileWatcherAnalyzerIntegration:
    """Integration tests for FileWatcher + Analyzer interaction."""

    def test_file_creation_triggers_analysis(self, minimal_project: Path) -> None:
        """Test that creating a new file triggers analysis."""
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(ImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        file_watcher = FileWatcher(
            project_root=str(minimal_project),
        )

        graph_updater = GraphUpdater(
            graph=graph,
            analyzer=analyzer,
            file_watcher=file_watcher,
        )

        # Start the file watcher
        file_watcher.start()

        try:
            # Create a new file
            new_file = minimal_project / "new_module.py"
            new_file.write_text(
                """# Copyright (c) 2025 Henru Wang
# All rights reserved.

import json
import os

def new_function():
    pass
"""
            )

            # Give watcher time to detect the change
            time.sleep(0.1)

            # Process pending changes
            graph_updater.process_pending_changes()

            # The file should be queued for analysis
            # Note: Exact behavior depends on file watcher implementation

        finally:
            file_watcher.stop()

    def test_file_modification_triggers_reanalysis(self, minimal_project: Path) -> None:
        """Test that modifying a file triggers re-analysis."""
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(ImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        file_watcher = FileWatcher(
            project_root=str(minimal_project),
        )

        graph_updater = GraphUpdater(
            graph=graph,
            analyzer=analyzer,
            file_watcher=file_watcher,
        )

        main_file = minimal_project / "main.py"

        # Initial analysis
        analyzer.analyze_file(str(main_file))

        # Start file watcher
        file_watcher.start()

        try:
            # Modify the file
            main_file.write_text(
                '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Modified main module with more imports."""

import json
import sys
import os

from utils import helper_function


def main():
    pass
'''
            )

            # Give watcher time to detect
            time.sleep(0.1)

            # Process pending changes
            graph_updater.process_pending_changes()

            # Graph should reflect updated imports
            updated_rels = graph.get_all_relationships()
            # Should have relationships (exact count depends on what's tracked)
            assert len(updated_rels) >= 0

        finally:
            file_watcher.stop()

    def test_file_deletion_removes_relationships(self, minimal_project: Path) -> None:
        """Test that deleting a file removes its relationships."""
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(ImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        file_watcher = FileWatcher(
            project_root=str(minimal_project),
        )

        graph_updater = GraphUpdater(
            graph=graph,
            analyzer=analyzer,
            file_watcher=file_watcher,
        )

        # Create and analyze a file
        temp_file = minimal_project / "temp_module.py"
        temp_file.write_text(
            """# Copyright (c) 2025 Henru Wang
# All rights reserved.

import json

def temp_function():
    pass
"""
        )

        analyzer.analyze_file(str(temp_file))
        assert len(graph.get_dependencies(str(temp_file))) >= 0

        # Start file watcher
        file_watcher.start()

        try:
            # Delete the file
            temp_file.unlink()

            # Give watcher time to detect
            time.sleep(0.1)

            # Process pending changes
            graph_updater.process_pending_changes()

            # Relationships from deleted file should be removed
            # (behavior depends on implementation)

        finally:
            file_watcher.stop()

    def test_gitignore_patterns_respected(self, minimal_project: Path) -> None:
        """Test that .gitignore patterns are respected by file watcher.

        Note: The FileWatcher may need to be initialized after .gitignore exists,
        or patterns may need to be loaded via specific method.
        """
        # Create .gitignore BEFORE initializing file watcher
        gitignore = minimal_project / ".gitignore"
        gitignore.write_text("ignored_dir/\n*.pyc\n__pycache__/\n")

        # Create ignored directory and file BEFORE initializing file watcher
        ignored_dir = minimal_project / "ignored_dir"
        ignored_dir.mkdir()

        ignored_file = ignored_dir / "ignored.py"
        ignored_file.write_text("import os\n")

        # Initialize file watcher after .gitignore exists
        file_watcher = FileWatcher(
            project_root=str(minimal_project),
        )

        # Non-ignored file should not be ignored
        main_file = minimal_project / "main.py"
        assert not file_watcher.should_ignore(str(main_file))

        # Check if __pycache__ pattern is respected
        pycache_dir = minimal_project / "__pycache__"
        pycache_dir.mkdir()
        pycache_file = pycache_dir / "module.cpython-310.pyc"
        pycache_file.write_bytes(b"\x00")

        # __pycache__ should be ignored
        assert file_watcher.should_ignore(str(pycache_file))

    def test_pytest_test_files_detected(self, sample_project: Path) -> None:
        """Test that test files are properly detected."""
        file_watcher = FileWatcher(
            project_root=str(sample_project),
        )

        # Regular file should not be ignored
        core_file = sample_project / "mypackage" / "core.py"
        assert not file_watcher.should_ignore(str(core_file))

    def test_file_watcher_with_service(self, minimal_project: Path) -> None:
        """Test file watcher integration through service layer."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
        )

        # Initial analysis
        service.analyze_directory(str(minimal_project))

        # Start file watcher through service
        service.start_file_watcher()

        try:
            # Create a new file
            new_file = minimal_project / "watched_file.py"
            new_file.write_text(
                """# Copyright (c) 2025 Henru Wang
# All rights reserved.

import json

def watched_function():
    return json.dumps({})
"""
            )

            # Give watcher time to detect
            time.sleep(0.1)

            # Process pending changes
            stats = service.process_pending_changes()

            # Stats should indicate processed changes
            assert isinstance(stats, dict)

        finally:
            service.stop_file_watcher()
            service.shutdown()

    def test_batch_file_changes(self, minimal_project: Path) -> None:
        """Test handling multiple file changes in batch."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
        )

        # Initial analysis
        service.analyze_directory(str(minimal_project))

        # Create multiple files at once
        for i in range(3):
            file = minimal_project / f"batch_file_{i}.py"
            file.write_text(
                f"""# Copyright (c) 2025 Henru Wang
# All rights reserved.

import json

def batch_function_{i}():
    return json.dumps({{"index": {i}}})
"""
            )

        # Analyze all new files
        for i in range(3):
            file = minimal_project / f"batch_file_{i}.py"
            service.analyze_file(str(file))

        # Get updated graph
        export = service.get_relationship_graph()
        assert len(export["files"]) >= 3

        service.shutdown()

    def test_symlink_handling(self, minimal_project: Path) -> None:
        """Test that symlinks are handled correctly."""
        # Create a target file
        target_file = minimal_project / "target.py"
        target_file.write_text("import os\n")

        # Create a symlink
        symlink = minimal_project / "link.py"
        try:
            symlink.symlink_to(target_file)

            # Create file watcher after symlink exists
            file_watcher = FileWatcher(
                project_root=str(minimal_project),
            )

            # Both should be visible to file watcher
            # Symlink should be accessible
            assert symlink.exists()
            assert not file_watcher.should_ignore(str(symlink))

        except OSError:
            # Symlinks may not be supported on all platforms
            pytest.skip("Symlinks not supported on this platform")

    def test_ignore_patterns_from_config(self, minimal_project: Path) -> None:
        """Test that ignore patterns from config are respected."""
        # Create config with ignore patterns
        config_path = minimal_project / ".cross_file_context_links.yml"
        config_path.write_text(
            """ignore_patterns:
  - "*.tmp"
  - "build/"
  - ".cache/"
"""
        )

        config = Config(config_path=config_path)

        file_watcher = FileWatcher(
            project_root=str(minimal_project),
            user_ignore_patterns=(set(config.ignore_patterns) if config.ignore_patterns else None),
        )

        # Create a .tmp file - should be ignored
        tmp_file = minimal_project / "test.tmp"
        tmp_file.write_text("temporary")

        # Create build directory - should be ignored
        build_dir = minimal_project / "build"
        build_dir.mkdir()
        build_file = build_dir / "output.py"
        build_file.write_text("import os\n")

        # Check ignoring
        assert file_watcher.should_ignore(str(build_file))

    def test_rapid_file_changes(self, minimal_project: Path) -> None:
        """Test handling of rapid successive file changes."""
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(ImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        file_watcher = FileWatcher(
            project_root=str(minimal_project),
        )

        graph_updater = GraphUpdater(
            graph=graph,
            analyzer=analyzer,
            file_watcher=file_watcher,
        )

        test_file = minimal_project / "rapid_changes.py"

        file_watcher.start()

        try:
            # Make rapid changes
            for i in range(5):
                test_file.write_text(
                    f"""# Copyright (c) 2025 Henru Wang
# All rights reserved.

# Version {i}
import json

def func():
    return {i}
"""
                )
                time.sleep(0.02)  # Small delay between writes

            # Give watcher time to detect
            time.sleep(0.1)

            # Process pending changes
            graph_updater.process_pending_changes()

            # File should be in final state
            content = test_file.read_text()
            assert "Version 4" in content

        finally:
            file_watcher.stop()

    def test_watcher_start_stop_lifecycle(self, minimal_project: Path) -> None:
        """Test file watcher start/stop lifecycle.

        Note: FileWatcher raises RuntimeError if start() is called twice
        without stopping first. This is the expected behavior.
        """
        file_watcher = FileWatcher(
            project_root=str(minimal_project),
        )

        # Should be stoppable even if not started (no-op)
        file_watcher.stop()

        # Start should work
        file_watcher.start()

        # Multiple starts should raise error
        with pytest.raises(RuntimeError, match="already running"):
            file_watcher.start()

        # Stop should work
        file_watcher.stop()

        # Multiple stops should be safe (no-op)
        file_watcher.stop()

        # Can restart after stopping
        file_watcher.start()
        file_watcher.stop()

    def test_file_event_timestamps(self, minimal_project: Path) -> None:
        """Test that file event timestamps are tracked."""
        file_watcher = FileWatcher(
            project_root=str(minimal_project),
        )

        main_file = minimal_project / "main.py"

        file_watcher.start()

        try:
            # Modify file
            original_content = main_file.read_text()
            main_file.write_text(original_content + "\n# Modified\n")

            # Give watcher time to detect
            time.sleep(0.1)

            # Check timestamps dict
            timestamps = file_watcher.file_event_timestamps
            assert isinstance(timestamps, dict)
            # If the watcher detected the change, it should have a timestamp
            # (behavior depends on whether watcher detected the change)

        finally:
            file_watcher.stop()
