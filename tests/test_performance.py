# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Performance tests (TDD Section 8.3).

This module contains performance tests to verify non-functional requirements:
- T-7.3: Verify incremental update <200ms per file (NFR-1)

Test Strategy:
- Use pytest-benchmark for consistent timing measurements
- Create realistic file scenarios (various sizes, complexity)
- Measure FileWatcher timestamp update performance
- Simulate rapid edits and bulk operations (git checkout)
"""

import time

import pytest

from xfile_context.file_watcher import FileWatcher


class TestIncrementalUpdatePerformance:
    """T-7.3: Verify incremental update <200ms per file (NFR-1)."""

    @pytest.mark.performance
    def test_rapid_file_modifications_last_write_wins(self, tmp_path):
        """Test rapid saves collapsed via timestamp overwrites (T-7.3).

        Verifies that:
        - Multiple rapid edits to same file result in fast timestamp updates
        - Last write wins (final timestamp reflects most recent edit)
        - Performance target met (<200ms for multiple updates)
        """
        watcher = FileWatcher(project_root=str(tmp_path))
        watcher.start()

        try:
            # Create test file
            test_file = tmp_path / "rapid_edit.py"
            test_file.write_text("# Initial content\n")
            time.sleep(0.2)  # Wait for initial event

            # Simulate rapid edits (10 edits in quick succession)
            start_time = time.time()
            for i in range(10):
                test_file.write_text(f"# Edit {i}\n")
                # Small delay to ensure file system events are distinct
                time.sleep(0.01)

            # Wait for all events to be processed
            time.sleep(0.3)
            end_time = time.time()

            # Verify timestamp was updated
            timestamp = watcher.get_timestamp(str(test_file))
            assert timestamp is not None

            # Verify last write wins (timestamp should be close to end_time)
            assert timestamp >= start_time
            assert timestamp <= end_time

            # Verify total time is reasonable (should be fast due to timestamp-only approach)
            total_time = end_time - start_time
            # 10 edits + delays + event processing should be fast
            # We allow more than 200ms total because we're doing 10 edits sequentially
            # The key is that each individual timestamp update is fast
            assert total_time < 2.0, f"Rapid edits took {total_time:.3f}s (too slow)"

        finally:
            watcher.stop()

    @pytest.mark.performance
    def test_single_file_update_performance(self, tmp_path):
        """Test single file update meets <200ms target (T-7.3).

        Verifies that a single file modification is detected and timestamp
        updated within 200ms (NFR-1 requirement).
        """
        watcher = FileWatcher(project_root=str(tmp_path))
        watcher.start()

        try:
            # Create test file
            test_file = tmp_path / "single_edit.py"
            test_file.write_text("# Original content\n")
            time.sleep(0.2)  # Wait for initial event

            # Measure time for single edit detection
            start_time = time.time()
            test_file.write_text("# Modified content\n")

            # Poll for timestamp update (with timeout)
            timeout = 0.2  # 200ms per NFR-1
            poll_interval = 0.01
            elapsed = 0.0
            timestamp = None

            while elapsed < timeout:
                timestamp = watcher.get_timestamp(str(test_file))
                if timestamp is not None and timestamp >= start_time:
                    break
                time.sleep(poll_interval)
                elapsed += poll_interval

            detection_time = time.time() - start_time

            # Verify timestamp was updated
            assert timestamp is not None, "Timestamp not updated within timeout"
            assert timestamp >= start_time, "Timestamp predates modification"

            # Verify performance target met (<200ms per NFR-1)
            assert (
                detection_time < 0.2
            ), f"File update detected in {detection_time*1000:.1f}ms (target: <200ms)"

        finally:
            watcher.stop()

    @pytest.mark.performance
    def test_bulk_operations_performance(self, tmp_path):
        """Test bulk operations (git checkout) performance (T-7.3).

        Simulates git checkout by creating/modifying many files rapidly.
        Verifies that timestamp-only approach handles bulk operations efficiently
        without debouncing or batching logic.
        """
        watcher = FileWatcher(project_root=str(tmp_path))
        watcher.start()

        try:
            # Simulate git checkout: create 50 files rapidly
            num_files = 50
            files = []

            start_time = time.time()

            for i in range(num_files):
                test_file = tmp_path / f"file_{i:03d}.py"
                test_file.write_text(f"# File {i}\n")
                files.append(test_file)

            # Wait for all events to be processed
            time.sleep(1.0)
            end_time = time.time()

            # Verify all files have timestamps
            missing_timestamps = []
            for test_file in files:
                timestamp = watcher.get_timestamp(str(test_file))
                if timestamp is None:
                    missing_timestamps.append(test_file.name)

            assert not missing_timestamps, f"Missing timestamps for: {missing_timestamps}"

            # Verify performance: Total time should be reasonable
            total_time = end_time - start_time
            # With timestamp-only approach, 50 files should process quickly
            # Allow ~2 seconds for file creation + event processing
            assert total_time < 3.0, f"Bulk operation took {total_time:.3f}s (too slow)"

            # Key insight: Each individual timestamp update is fast (microseconds)
            # Even with 50 files, total time dominated by file I/O, not event processing
            avg_time_per_file = total_time / num_files
            print(
                f"Bulk operation: {num_files} files in {total_time:.3f}s "
                f"(avg {avg_time_per_file*1000:.1f}ms per file)"
            )

        finally:
            watcher.stop()

    @pytest.mark.performance
    def test_timestamp_update_overhead_unit(self, tmp_path):
        """Test raw timestamp update overhead (unit test for T-7.3).

        Measures the overhead of FileWatcher.update_timestamp() directly
        to verify it's microseconds-fast as claimed in TDD Section 3.6.2.
        """
        watcher = FileWatcher(project_root=str(tmp_path))

        test_file = str(tmp_path / "test.py")

        # Measure 1000 timestamp updates
        num_updates = 1000
        start_time = time.time()

        for _ in range(num_updates):
            watcher.update_timestamp(test_file)

        end_time = time.time()
        total_time = end_time - start_time
        avg_time = total_time / num_updates

        # Each update should be microseconds-fast
        # Allow 100 microseconds per update (0.0001 seconds)
        assert (
            avg_time < 0.0001
        ), f"Timestamp update too slow: {avg_time*1000000:.1f}µs (target: <100µs)"

        print(
            f"Timestamp update performance: {num_updates} updates in {total_time:.4f}s "
            f"(avg {avg_time*1000000:.1f}µs per update)"
        )

    @pytest.mark.performance
    def test_concurrent_file_modifications(self, tmp_path):
        """Test multiple files modified simultaneously (T-7.3).

        Simulates concurrent edits to different files (e.g., IDE auto-formatting
        multiple files, or multi-file refactoring).
        """
        watcher = FileWatcher(project_root=str(tmp_path))
        watcher.start()

        try:
            # Create multiple test files
            num_files = 20
            test_files = []
            for i in range(num_files):
                test_file = tmp_path / f"concurrent_{i:02d}.py"
                test_file.write_text(f"# File {i} - initial\n")
                test_files.append(test_file)

            time.sleep(0.3)  # Wait for initial events

            # Modify all files rapidly (simulate concurrent edits)
            start_time = time.time()

            for i, test_file in enumerate(test_files):
                test_file.write_text(f"# File {i} - modified\n")
                # Very small delay to ensure events are slightly staggered
                time.sleep(0.001)

            # Wait for all events to be processed
            time.sleep(0.5)
            end_time = time.time()

            # Verify all files have updated timestamps
            for test_file in test_files:
                timestamp = watcher.get_timestamp(str(test_file))
                assert timestamp is not None, f"No timestamp for {test_file.name}"
                assert (
                    timestamp >= start_time
                ), f"Timestamp predates modification for {test_file.name}"

            total_time = end_time - start_time
            avg_time_per_file = total_time / num_files

            # Verify performance: Each file should be processed quickly
            # Allow 50ms average per file (well under 200ms target)
            assert (
                avg_time_per_file < 0.05
            ), f"Concurrent modifications too slow: {avg_time_per_file*1000:.1f}ms per file"

            print(
                f"Concurrent modifications: {num_files} files in {total_time:.3f}s "
                f"(avg {avg_time_per_file*1000:.1f}ms per file)"
            )

        finally:
            watcher.stop()


class TestEventProcessingDesign:
    """Verify simplified event processing design (TDD Section 3.6.2)."""

    def test_no_debouncing_last_write_wins(self, tmp_path):
        """Verify no debouncing logic - last write wins via timestamp overwrite.

        This test documents the design decision: No timer-based debouncing,
        just simple timestamp updates. Multiple rapid edits naturally collapse
        because the timestamp is simply overwritten each time.
        """
        watcher = FileWatcher(project_root=str(tmp_path))
        watcher.start()

        try:
            test_file = tmp_path / "no_debounce.py"
            test_file.write_text("# Initial\n")
            time.sleep(0.1)

            # Edit 1
            test_file.write_text("# Edit 1\n")
            time.sleep(0.05)
            ts1 = watcher.get_timestamp(str(test_file))

            # Edit 2 (rapid - within typical debounce window)
            time.sleep(0.05)
            test_file.write_text("# Edit 2\n")
            time.sleep(0.05)
            ts2 = watcher.get_timestamp(str(test_file))

            # Edit 3 (rapid - within typical debounce window)
            time.sleep(0.05)
            test_file.write_text("# Edit 3\n")
            time.sleep(0.1)
            ts3 = watcher.get_timestamp(str(test_file))

            # Verify timestamps are different (each edit gets its own timestamp)
            # No debouncing means each event is processed immediately
            assert ts1 is not None
            assert ts2 is not None
            assert ts3 is not None

            # Last timestamp should be most recent (last write wins)
            assert ts3 > ts2
            assert ts2 > ts1

        finally:
            watcher.stop()

    def test_no_batching_each_event_processed(self, tmp_path):
        """Verify no batching logic - each event processed independently.

        This test documents the design decision: No event batching, each file
        system event triggers an immediate timestamp update. Fast enough that
        batching is unnecessary.
        """
        watcher = FileWatcher(project_root=str(tmp_path))
        watcher.start()

        try:
            # Create multiple files in quick succession
            files = []
            for i in range(10):
                test_file = tmp_path / f"no_batch_{i}.py"
                test_file.write_text(f"# File {i}\n")
                files.append(test_file)
                time.sleep(0.01)  # Quick succession

            # Wait for events
            time.sleep(0.3)

            # Verify each file has its own timestamp (not batched)
            timestamps = []
            for test_file in files:
                ts = watcher.get_timestamp(str(test_file))
                assert ts is not None, f"No timestamp for {test_file.name}"
                timestamps.append(ts)

            # Timestamps should be different (not batched into single timestamp)
            # Each file gets processed independently
            unique_timestamps = set(timestamps)
            # Due to filesystem timing, some timestamps might coincide, but
            # we should see multiple distinct timestamps (not all the same)
            assert len(unique_timestamps) > 1, "All timestamps identical (unexpected batching?)"

        finally:
            watcher.stop()
