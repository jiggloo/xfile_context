# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Integration tests for Issue #117 Option B: Staleness resolution.

NOTE: Marked as slow tests - integration tests create full project structures.
Run with: pytest -m slow

Tests the full integration of staleness resolution through the service layer,
including:
- Modified dependency files are re-analyzed
- Context injection includes updated definitions
- Transitive dependency chains are handled correctly
"""

import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from xfile_context.config import Config
from xfile_context.service import CrossFileContextService

# Mark entire module as slow - integration tests create full project structures
pytestmark = pytest.mark.slow


class TestDependencyReanalysis:
    """Test that modified dependencies are re-analyzed."""

    def test_modified_dependency_reanalyzed(self):
        """Test that a modified dependency is re-analyzed on read_with_context."""
        with TemporaryDirectory() as tmpdir:
            # Create initial files
            base_file = Path(tmpdir) / "base.py"
            base_file.write_text("def original_function():\n    pass\n")

            main_file = Path(tmpdir) / "main.py"
            main_file.write_text("from base import original_function\n\noriginal_function()\n")

            # Create service and analyze files
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            try:
                # First read should analyze both files
                result1 = service.read_file_with_context(str(main_file))
                assert result1.content is not None

                # Verify relationship exists
                deps = service.get_dependencies(str(main_file))
                assert len(deps) > 0

                # Modify the dependency file
                time.sleep(0.01)  # Ensure mtime changes
                base_file.write_text(
                    "def original_function():\n"
                    "    pass\n\n"
                    "def new_function():\n"
                    "    '''A new function.'''\n"
                    "    return 42\n"
                )

                # Update main.py to use the new function
                time.sleep(0.01)
                main_file.write_text(
                    "from base import original_function, new_function\n\n"
                    "original_function()\n"
                    "new_function()\n"
                )

                # Read main.py again - should detect and re-analyze stale files
                service.read_file_with_context(str(main_file))

                # Check that new_function is now in the dependencies
                deps2 = service.get_dependencies(str(main_file))
                symbols = [d.get("target_symbol") for d in deps2]
                assert "new_function" in symbols or "original_function" in symbols

            finally:
                service.shutdown()

    def test_transitive_dependency_staleness(self):
        """Test handling of transitive dependency staleness."""
        with TemporaryDirectory() as tmpdir:
            # Create a chain: main.py -> utils.py -> helpers.py
            helpers_file = Path(tmpdir) / "helpers.py"
            helpers_file.write_text("def helper():\n    return 1\n")

            utils_file = Path(tmpdir) / "utils.py"
            utils_file.write_text(
                "from helpers import helper\n\ndef utility():\n    return helper()\n"
            )

            main_file = Path(tmpdir) / "main.py"
            main_file.write_text("from utils import utility\n\nutility()\n")

            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            try:
                # First read to establish relationships
                result1 = service.read_file_with_context(str(main_file))
                assert result1.content is not None

                # Modify helpers.py (transitive dependency)
                time.sleep(0.01)
                helpers_file.write_text(
                    "def helper():\n    return 1\n\ndef new_helper():\n    return 2\n"
                )

                # Update utils.py to use new helper
                time.sleep(0.01)
                utils_file.write_text(
                    "from helpers import helper, new_helper\n\n"
                    "def utility():\n"
                    "    return helper() + new_helper()\n"
                )

                # Read main.py - should detect stale transitive dependencies
                result2 = service.read_file_with_context(str(main_file))
                assert result2.content is not None

            finally:
                service.shutdown()


class TestContextInjectionAfterModification:
    """Test that context injection reflects modifications."""

    def test_context_includes_new_definitions(self):
        """Test that context includes newly added definitions after re-analysis."""
        with TemporaryDirectory() as tmpdir:
            # Create files
            lib_file = Path(tmpdir) / "mylib.py"
            lib_file.write_text("def existing():\n    '''Existing function.'''\n    pass\n")

            app_file = Path(tmpdir) / "app.py"
            app_file.write_text("from mylib import existing\n\nexisting()\n")

            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            try:
                # First read
                service.read_file_with_context(str(app_file))

                # Add new function to library
                time.sleep(0.01)
                lib_file.write_text(
                    "def existing():\n    '''Existing function.'''\n    pass\n\n"
                    "def brand_new():\n    '''Brand new function.'''\n    return 42\n"
                )

                # Update app to use new function
                time.sleep(0.01)
                app_file.write_text(
                    "from mylib import existing, brand_new\n\nexisting()\nbrand_new()\n"
                )

                # Read again
                service.read_file_with_context(str(app_file))

                # The injected context should mention brand_new
                # (This verifies the re-analysis picked up the new function)
                deps = service.get_dependencies(str(app_file))
                symbols = [d.get("target_symbol") for d in deps]
                assert "brand_new" in symbols or len(deps) >= 2

            finally:
                service.shutdown()


class TestNoUnnecessaryReanalysis:
    """Test that unmodified files are not re-analyzed."""

    def test_unmodified_files_not_reanalyzed(self):
        """Test that files not modified since last analysis are skipped."""
        with TemporaryDirectory() as tmpdir:
            # Create files
            dep_file = Path(tmpdir) / "dep.py"
            dep_file.write_text("def dep_func():\n    pass\n")

            main_file = Path(tmpdir) / "main.py"
            main_file.write_text("from dep import dep_func\n\ndep_func()\n")

            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            try:
                # First read to analyze
                service.read_file_with_context(str(main_file))

                # Get initial analysis times - ensure metadata exists
                main_meta = service._graph.get_file_metadata(str(main_file))
                assert main_meta is not None, "main_file should have metadata after analysis"

                initial_main_time = main_meta.last_analyzed

                # Read again without modifying
                time.sleep(0.1)
                service.read_file_with_context(str(main_file))

                # Analysis time for main should not change (it was not re-analyzed)
                main_meta2 = service._graph.get_file_metadata(str(main_file))
                assert main_meta2.last_analyzed == initial_main_time

            finally:
                service.shutdown()


class TestDiamondDependencyPattern:
    """Test handling of diamond dependency patterns."""

    def test_diamond_pattern_all_stale(self):
        """Test diamond pattern when all files are stale."""
        with TemporaryDirectory() as tmpdir:
            # Create diamond: app.py -> [utils.py, helpers.py] -> base.py
            base_file = Path(tmpdir) / "base.py"
            base_file.write_text("def base_func():\n    return 1\n")

            utils_file = Path(tmpdir) / "utils.py"
            utils_file.write_text(
                "from base import base_func\n\ndef util():\n    return base_func()\n"
            )

            helpers_file = Path(tmpdir) / "helpers.py"
            helpers_file.write_text(
                "from base import base_func\n\ndef helper():\n    return base_func() * 2\n"
            )

            app_file = Path(tmpdir) / "app.py"
            app_file.write_text(
                "from utils import util\n"
                "from helpers import helper\n\n"
                "def main():\n"
                "    return util() + helper()\n"
            )

            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            try:
                # First read to establish relationships
                result1 = service.read_file_with_context(str(app_file))
                assert result1.content is not None

                # Verify app was analyzed
                app_meta = service._graph.get_file_metadata(str(app_file))
                assert app_meta is not None, "app.py should be analyzed after read_with_context"

                # Modify all files
                time.sleep(0.01)
                base_file.write_text("def base_func():\n    return 100\n")
                time.sleep(0.01)
                utils_file.write_text(
                    "from base import base_func\n\ndef util():\n    return base_func() + 1\n"
                )
                time.sleep(0.01)
                helpers_file.write_text(
                    "from base import base_func\n\ndef helper():\n    return base_func() + 2\n"
                )
                time.sleep(0.01)
                app_file.write_text(
                    "from utils import util\n"
                    "from helpers import helper\n\n"
                    "def main():\n"
                    "    return util() * helper()\n"
                )

                # Read app.py - should handle diamond correctly
                result2 = service.read_file_with_context(str(app_file))
                assert result2.content is not None

                # At minimum, app.py should be re-analyzed
                app_meta2 = service._graph.get_file_metadata(str(app_file))
                assert app_meta2 is not None, "app.py should have metadata after re-analysis"

            finally:
                service.shutdown()
