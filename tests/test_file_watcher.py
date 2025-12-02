# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for FileWatcher."""

import time

import pytest

from xfile_context.file_watcher import FileWatcher


class TestFileWatcher:
    """Tests for FileWatcher timestamp tracking and filtering."""

    def test_initialization(self, tmp_path):
        """Test FileWatcher initialization."""
        watcher = FileWatcher(project_root=str(tmp_path))

        assert watcher.project_root == tmp_path.resolve()
        assert watcher.file_event_timestamps == {}
        assert not watcher.is_running()

    def test_gitignore_loading(self, tmp_path):
        """Test loading .gitignore patterns."""
        # Create .gitignore file
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text(
            """
# Comment line
*.pyc
__pycache__/
build/
*.log

# Another comment
temp_*
"""
        )

        watcher = FileWatcher(project_root=str(tmp_path))

        # Check that patterns were loaded (excluding comments and empty lines)
        assert len(watcher._gitignore_patterns) == 5
        assert "*.pyc" in watcher._gitignore_patterns
        assert "__pycache__/" in watcher._gitignore_patterns
        assert "build/" in watcher._gitignore_patterns
        assert "*.log" in watcher._gitignore_patterns
        assert "temp_*" in watcher._gitignore_patterns

    def test_gitignore_missing(self, tmp_path):
        """Test initialization when .gitignore doesn't exist."""
        watcher = FileWatcher(project_root=str(tmp_path))

        assert len(watcher._gitignore_patterns) == 0

    def test_gitignore_pattern_length_validation(self, tmp_path):
        """Test that overly long gitignore patterns are rejected."""
        gitignore = tmp_path / ".gitignore"

        # Create patterns of various lengths
        valid_pattern = "a" * 1000  # Exactly at limit
        invalid_pattern = "b" * 1001  # Over limit

        gitignore.write_text(f"{valid_pattern}\n{invalid_pattern}\n*.pyc\n")

        watcher = FileWatcher(project_root=str(tmp_path))

        # Valid pattern should be loaded
        assert valid_pattern in watcher._gitignore_patterns
        # Invalid pattern should be skipped
        assert invalid_pattern not in watcher._gitignore_patterns
        # Normal patterns should still work
        assert "*.pyc" in watcher._gitignore_patterns

    def test_should_ignore_always_ignored(self, tmp_path):
        """Test hardcoded always-ignored patterns (NFR-8)."""
        watcher = FileWatcher(project_root=str(tmp_path))

        # Test always-ignored directories
        assert watcher.should_ignore(str(tmp_path / ".git" / "config"))
        assert watcher.should_ignore(str(tmp_path / "__pycache__" / "test.pyc"))
        assert watcher.should_ignore(str(tmp_path / ".venv" / "bin" / "python"))
        assert watcher.should_ignore(str(tmp_path / "node_modules" / "package.json"))
        assert watcher.should_ignore(str(tmp_path / ".pytest_cache" / "v" / "cache"))
        assert watcher.should_ignore(str(tmp_path / ".mypy_cache" / "3.8"))

        # Test egg-info pattern
        assert watcher.should_ignore(str(tmp_path / "foo.egg-info" / "PKG-INFO"))

    def test_should_ignore_sensitive_files(self, tmp_path):
        """Test sensitive file patterns are ignored."""
        watcher = FileWatcher(project_root=str(tmp_path))

        # Test basic sensitive files
        assert watcher.should_ignore(str(tmp_path / ".env"))
        assert watcher.should_ignore(str(tmp_path / ".env.local"))
        assert watcher.should_ignore(str(tmp_path / "credentials.json"))
        assert watcher.should_ignore(str(tmp_path / "private.key"))
        assert watcher.should_ignore(str(tmp_path / "certificate.pem"))
        assert watcher.should_ignore(str(tmp_path / "api_key"))
        assert watcher.should_ignore(str(tmp_path / "db_secret"))

        # Test SSH keys (all types)
        assert watcher.should_ignore(str(tmp_path / ".ssh" / "id_rsa"))
        assert watcher.should_ignore(str(tmp_path / ".ssh" / "id_dsa"))
        assert watcher.should_ignore(str(tmp_path / ".ssh" / "id_ecdsa"))
        assert watcher.should_ignore(str(tmp_path / ".ssh" / "id_ed25519"))

        # Test Java keystores
        assert watcher.should_ignore(str(tmp_path / "keystore.jks"))
        assert watcher.should_ignore(str(tmp_path / "app.keystore"))
        assert watcher.should_ignore(str(tmp_path / "trust.truststore"))

        # Test certificates
        assert watcher.should_ignore(str(tmp_path / "server.cer"))
        assert watcher.should_ignore(str(tmp_path / "client.crt"))

        # Test PKCS12 keystores
        assert watcher.should_ignore(str(tmp_path / "cert.p12"))
        assert watcher.should_ignore(str(tmp_path / "identity.pfx"))

        # Test secrets files
        assert watcher.should_ignore(str(tmp_path / "secrets.yaml"))
        assert watcher.should_ignore(str(tmp_path / "secrets.yml"))

        # Test package manager credentials
        assert watcher.should_ignore(str(tmp_path / ".npmrc"))
        assert watcher.should_ignore(str(tmp_path / ".pypirc"))

        # Test cloud credentials
        assert watcher.should_ignore(str(tmp_path / "gcloud.json"))
        assert watcher.should_ignore(str(tmp_path / ".aws" / "credentials"))

    def test_should_ignore_gitignore_patterns(self, tmp_path):
        """Test .gitignore patterns are respected (NFR-7)."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\ntemp_*\nbuild/\n")

        watcher = FileWatcher(project_root=str(tmp_path))

        # Test gitignore patterns
        assert watcher.should_ignore(str(tmp_path / "debug.log"))
        assert watcher.should_ignore(str(tmp_path / "temp_file.txt"))
        assert watcher.should_ignore(str(tmp_path / "build" / "output.py"))

        # Test non-ignored files
        assert not watcher.should_ignore(str(tmp_path / "main.py"))
        assert not watcher.should_ignore(str(tmp_path / "src" / "module.py"))

    def test_should_ignore_user_patterns(self, tmp_path):
        """Test user-configured ignore patterns."""
        user_patterns = {"generated/**/*.py", "vendor/*.py"}
        watcher = FileWatcher(project_root=str(tmp_path), user_ignore_patterns=user_patterns)

        # Test user patterns
        assert watcher.should_ignore(str(tmp_path / "generated" / "api" / "models.py"))
        assert watcher.should_ignore(str(tmp_path / "vendor" / "library.py"))

        # Test non-ignored files
        assert not watcher.should_ignore(str(tmp_path / "src" / "main.py"))

    def test_is_supported_file(self, tmp_path):
        """Test extension-based file filtering."""
        watcher = FileWatcher(project_root=str(tmp_path))

        # Test supported extensions (.py for v0.1.0)
        assert watcher.is_supported_file(str(tmp_path / "main.py"))
        assert watcher.is_supported_file(str(tmp_path / "src" / "module.py"))

        # Test unsupported extensions
        assert not watcher.is_supported_file(str(tmp_path / "README.md"))
        assert not watcher.is_supported_file(str(tmp_path / "package.json"))
        assert not watcher.is_supported_file(str(tmp_path / "script.sh"))
        assert not watcher.is_supported_file(str(tmp_path / "main.ts"))  # Future support
        assert not watcher.is_supported_file(str(tmp_path / "app.js"))  # Future support

    def test_get_language(self, tmp_path):
        """Test language identification from extension (DD-2)."""
        watcher = FileWatcher(project_root=str(tmp_path))

        # Test supported languages
        assert watcher.get_language(str(tmp_path / "main.py")) == "python"
        assert watcher.get_language(str(tmp_path / "src" / "module.py")) == "python"

        # Test unsupported extensions return None
        assert watcher.get_language(str(tmp_path / "main.ts")) is None
        assert watcher.get_language(str(tmp_path / "app.js")) is None
        assert watcher.get_language(str(tmp_path / "README.md")) is None

    def test_update_and_get_timestamp(self, tmp_path):
        """Test timestamp tracking for file events."""
        watcher = FileWatcher(project_root=str(tmp_path))

        test_file = str(tmp_path / "test.py")

        # Initially no timestamp
        assert watcher.get_timestamp(test_file) is None

        # Update timestamp
        before = time.time()
        watcher.update_timestamp(test_file)
        after = time.time()

        timestamp = watcher.get_timestamp(test_file)
        assert timestamp is not None
        assert before <= timestamp <= after

        # Update again (simulate file modification)
        time.sleep(0.01)  # Ensure different timestamp
        before2 = time.time()
        watcher.update_timestamp(test_file)
        after2 = time.time()

        timestamp2 = watcher.get_timestamp(test_file)
        assert timestamp2 is not None
        assert timestamp2 > timestamp  # Last write wins
        assert before2 <= timestamp2 <= after2

    def test_start_and_stop(self, tmp_path):
        """Test starting and stopping the file watcher."""
        watcher = FileWatcher(project_root=str(tmp_path))

        assert not watcher.is_running()

        # Start watcher
        watcher.start()
        assert watcher.is_running()

        # Stop watcher
        watcher.stop()
        time.sleep(0.1)  # Give observer time to stop
        assert not watcher.is_running()

    def test_start_already_running(self, tmp_path):
        """Test error when starting already running watcher."""
        watcher = FileWatcher(project_root=str(tmp_path))

        watcher.start()
        assert watcher.is_running()

        # Try to start again
        with pytest.raises(RuntimeError, match="already running"):
            watcher.start()

        watcher.stop()

    @pytest.mark.integration
    def test_file_create_event(self, tmp_path):
        """Test file creation event triggers timestamp update."""
        watcher = FileWatcher(project_root=str(tmp_path))
        watcher.start()

        try:
            # Create a Python file
            test_file = tmp_path / "new_file.py"
            test_file.write_text("# Test file\n")

            # Wait for event to be processed
            time.sleep(0.2)

            # Check timestamp was updated
            timestamp = watcher.get_timestamp(str(test_file))
            assert timestamp is not None
        finally:
            watcher.stop()

    @pytest.mark.integration
    def test_file_modify_event(self, tmp_path):
        """Test file modification event triggers timestamp update."""
        # Create file before starting watcher
        test_file = tmp_path / "existing.py"
        test_file.write_text("# Original content\n")

        watcher = FileWatcher(project_root=str(tmp_path))
        watcher.start()

        try:
            # Get initial timestamp (should be None as watcher wasn't running during creation)
            initial_timestamp = watcher.get_timestamp(str(test_file))

            # Modify the file
            time.sleep(0.1)
            test_file.write_text("# Modified content\n")

            # Wait for event to be processed
            time.sleep(0.2)

            # Check timestamp was updated
            new_timestamp = watcher.get_timestamp(str(test_file))
            assert new_timestamp is not None
            if initial_timestamp is not None:
                assert new_timestamp > initial_timestamp
        finally:
            watcher.stop()

    @pytest.mark.integration
    def test_file_delete_event(self, tmp_path):
        """Test file deletion event triggers timestamp update."""
        # Create file before starting watcher
        test_file = tmp_path / "to_delete.py"
        test_file.write_text("# Will be deleted\n")

        watcher = FileWatcher(project_root=str(tmp_path))
        watcher.start()

        try:
            # Delete the file
            test_file.unlink()

            # Wait for event to be processed
            time.sleep(0.2)

            # Check timestamp was updated (entry persists after deletion)
            timestamp = watcher.get_timestamp(str(test_file))
            assert timestamp is not None
        finally:
            watcher.stop()

    @pytest.mark.integration
    def test_file_move_event(self, tmp_path):
        """Test file move/rename event (treated as delete + create)."""
        # Create file before starting watcher
        old_file = tmp_path / "old_name.py"
        old_file.write_text("# Test file\n")

        watcher = FileWatcher(project_root=str(tmp_path))
        watcher.start()

        try:
            # Rename the file
            new_file = tmp_path / "new_name.py"
            old_file.rename(new_file)

            # Wait for event to be processed
            time.sleep(0.2)

            # Check both old and new paths have timestamps
            old_timestamp = watcher.get_timestamp(str(old_file))
            new_timestamp = watcher.get_timestamp(str(new_file))

            assert old_timestamp is not None  # Old path marked as deleted
            assert new_timestamp is not None  # New path marked as created
        finally:
            watcher.stop()

    @pytest.mark.integration
    def test_ignored_files_not_tracked(self, tmp_path):
        """Test that ignored files don't trigger timestamp updates."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n")

        watcher = FileWatcher(project_root=str(tmp_path))
        watcher.start()

        try:
            # Create ignored file (.log)
            log_file = tmp_path / "debug.log"
            log_file.write_text("Log content\n")

            # Create file in ignored directory
            cache_dir = tmp_path / "__pycache__"
            cache_dir.mkdir()
            cache_file = cache_dir / "module.pyc"
            cache_file.write_text("bytecode\n")

            # Wait for events to be processed
            time.sleep(0.2)

            # Check that ignored files have no timestamps
            assert watcher.get_timestamp(str(log_file)) is None
            assert watcher.get_timestamp(str(cache_file)) is None
        finally:
            watcher.stop()

    @pytest.mark.integration
    def test_unsupported_extensions_not_tracked(self, tmp_path):
        """Test that unsupported file extensions don't trigger updates."""
        watcher = FileWatcher(project_root=str(tmp_path))
        watcher.start()

        try:
            # Create files with unsupported extensions
            md_file = tmp_path / "README.md"
            md_file.write_text("# README\n")

            js_file = tmp_path / "script.js"
            js_file.write_text("console.log('test');\n")

            # Wait for events to be processed
            time.sleep(0.2)

            # Check that unsupported files have no timestamps
            assert watcher.get_timestamp(str(md_file)) is None
            assert watcher.get_timestamp(str(js_file)) is None
        finally:
            watcher.stop()

    @pytest.mark.integration
    def test_supported_python_files_tracked(self, tmp_path):
        """Test that Python files are correctly tracked."""
        watcher = FileWatcher(project_root=str(tmp_path))
        watcher.start()

        try:
            # Create Python files
            py_file = tmp_path / "main.py"
            py_file.write_text("print('hello')\n")

            src_dir = tmp_path / "src"
            src_dir.mkdir()
            module_file = src_dir / "module.py"
            module_file.write_text("def foo(): pass\n")

            # Wait for events to be processed
            time.sleep(0.2)

            # Check that Python files have timestamps
            assert watcher.get_timestamp(str(py_file)) is not None
            assert watcher.get_timestamp(str(module_file)) is not None
        finally:
            watcher.stop()


class TestFileWatcherExtensibility:
    """Test language-agnostic design (DD-2) with mock TypeScript analyzer."""

    def test_extensible_to_typescript(self, tmp_path):
        """Test that design is extensible to TypeScript (validates DD-2).

        This test validates the language-agnostic design by simulating
        TypeScript support. In production, TypeScript would be added by:
        1. Adding ".ts" to SUPPORTED_EXTENSIONS
        2. Implementing TypeScriptAnalyzer
        3. Registering analyzer in dispatch logic
        """
        # Simulate adding TypeScript support
        watcher = FileWatcher(project_root=str(tmp_path))

        # Monkey-patch to add TypeScript support (simulates future extension)
        original_extensions = watcher.SUPPORTED_EXTENSIONS.copy()
        watcher.SUPPORTED_EXTENSIONS[".ts"] = "typescript"

        try:
            # Test TypeScript file detection
            ts_file = tmp_path / "app.ts"
            assert watcher.is_supported_file(str(ts_file))
            assert watcher.get_language(str(ts_file)) == "typescript"

            # Test that ignore patterns work for TypeScript too
            assert watcher.should_ignore(str(tmp_path / "node_modules" / "lib.ts"))

            # Test timestamp tracking works for TypeScript
            watcher.update_timestamp(str(ts_file))
            assert watcher.get_timestamp(str(ts_file)) is not None
        finally:
            # Restore original extensions
            watcher.SUPPORTED_EXTENSIONS = original_extensions

    @pytest.mark.integration
    def test_mock_typescript_integration(self, tmp_path):
        """Integration test with mock TypeScript analyzer (validates DD-2 and T-9.3).

        This test validates:
        - DD-2: Language-agnostic watcher can dispatch to different analyzers
        - T-9.3: File watcher integration test requirement

        In a full implementation, this would dispatch to TypeScriptAnalyzer,
        but we use mocking to validate the extensibility without implementing
        the full TypeScript analyzer.
        """
        watcher = FileWatcher(project_root=str(tmp_path))

        # Simulate TypeScript support (would be in SUPPORTED_EXTENSIONS in production)
        watcher.SUPPORTED_EXTENSIONS[".ts"] = "typescript"

        watcher.start()

        try:
            # Create TypeScript file
            ts_file = tmp_path / "component.ts"
            ts_file.write_text("export class Component {}\n")

            # Wait for event
            time.sleep(0.2)

            # Verify watcher tracked the file
            timestamp = watcher.get_timestamp(str(ts_file))
            assert timestamp is not None

            # Verify language detection
            language = watcher.get_language(str(ts_file))
            assert language == "typescript"

            # In production, this would trigger TypeScriptAnalyzer dispatch
            # For this test, we validate that the watcher infrastructure works
            # for multiple languages without Python-specific logic
        finally:
            watcher.stop()
            # Clean up mock extension
            del watcher.SUPPORTED_EXTENSIONS[".ts"]

    def test_multiple_languages_simultaneously(self, tmp_path):
        """Test handling multiple languages simultaneously (validates DD-2)."""
        watcher = FileWatcher(project_root=str(tmp_path))

        # Add mock languages
        watcher.SUPPORTED_EXTENSIONS[".ts"] = "typescript"
        watcher.SUPPORTED_EXTENSIONS[".js"] = "javascript"

        watcher.start()

        try:
            # Create files in different languages
            py_file = tmp_path / "main.py"
            py_file.write_text("print('python')\n")

            ts_file = tmp_path / "app.ts"
            ts_file.write_text("console.log('typescript');\n")

            js_file = tmp_path / "script.js"
            js_file.write_text("console.log('javascript');\n")

            # Wait for events
            time.sleep(0.2)

            # Verify all languages are tracked independently
            assert watcher.get_timestamp(str(py_file)) is not None
            assert watcher.get_timestamp(str(ts_file)) is not None
            assert watcher.get_timestamp(str(js_file)) is not None

            # Verify correct language detection
            assert watcher.get_language(str(py_file)) == "python"
            assert watcher.get_language(str(ts_file)) == "typescript"
            assert watcher.get_language(str(js_file)) == "javascript"
        finally:
            watcher.stop()
            # Clean up mock extensions
            del watcher.SUPPORTED_EXTENSIONS[".ts"]
            del watcher.SUPPORTED_EXTENSIONS[".js"]
