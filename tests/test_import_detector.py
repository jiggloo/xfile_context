# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for ImportDetector plugin.

Tests cover:
- Import statement detection (import, from...import)
- Relative import detection
- Module resolution (project-local, stdlib, third-party)
- Edge cases (ambiguity, unresolved imports)
"""

import ast
import tempfile
from pathlib import Path

from xfile_context.detectors import ImportDetector
from xfile_context.models import RelationshipType


class TestImportDetectorBasics:
    """Tests for basic import detection functionality."""

    def test_detector_name(self):
        """Test detector name is 'ImportDetector'."""
        detector = ImportDetector()
        assert detector.name() == "ImportDetector"

    def test_detector_priority(self):
        """Test detector has high priority (100) as foundation detector."""
        detector = ImportDetector()
        assert detector.priority() == 100

    def test_no_imports_returns_empty_list(self):
        """Test that code with no imports returns empty relationship list."""
        detector = ImportDetector()
        code = """
x = 1
y = 2
print(x + y)
"""
        tree = ast.parse(code)
        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert relationships == []


class TestBasicImportStatements:
    """Tests for 'import module' statements."""

    def test_simple_import_statement(self):
        """Test detection of simple 'import module' statement."""
        detector = ImportDetector()
        code = "import os"
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.relationship_type == RelationshipType.IMPORT
        assert rel.source_file == "/test/file.py"
        assert rel.target_file == "<stdlib:os>"
        assert rel.line_number == 1
        assert rel.target_symbol == "os"
        assert rel.metadata["import_style"] == "import"
        assert rel.metadata["module_name"] == "os"

    def test_multiple_imports_in_one_statement(self):
        """Test 'import module1, module2' creates multiple relationships."""
        detector = ImportDetector()
        code = "import os, sys, json"
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should create 3 relationships
        assert len(relationships) == 3
        modules = {rel.metadata["module_name"] for rel in relationships}
        assert modules == {"os", "sys", "json"}

        # All should be stdlib
        for rel in relationships:
            assert rel.target_file.startswith("<stdlib:")

    def test_package_import(self):
        """Test 'import package.submodule' statement."""
        detector = ImportDetector()
        code = "import collections.abc"
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.target_file == "<stdlib:collections.abc>"
        assert rel.metadata["module_name"] == "collections.abc"


class TestFromImportStatements:
    """Tests for 'from module import name' statements."""

    def test_from_import_statement(self):
        """Test detection of 'from module import name' statement."""
        detector = ImportDetector()
        code = "from os import path"
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.relationship_type == RelationshipType.IMPORT
        assert rel.target_file == "<stdlib:os>"
        assert rel.target_symbol == "path"
        assert rel.metadata["import_style"] == "from_import"
        assert rel.metadata["module_name"] == "os"

    def test_from_import_multiple_names(self):
        """Test 'from module import name1, name2' creates multiple relationships."""
        detector = ImportDetector()
        code = "from typing import List, Dict, Optional"
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert len(relationships) == 3
        imported_names = {rel.target_symbol for rel in relationships}
        assert imported_names == {"List", "Dict", "Optional"}

        # All should have same target file
        for rel in relationships:
            assert rel.target_file == "<stdlib:typing>"
            assert rel.metadata["import_style"] == "from_import"

    def test_from_package_import(self):
        """Test 'from package.module import name' statement."""
        detector = ImportDetector()
        code = "from collections.abc import Iterable"
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.target_file == "<stdlib:collections.abc>"
        assert rel.metadata["module_name"] == "collections.abc"


class TestRelativeImports:
    """Tests for relative import statements."""

    def test_relative_import_single_dot(self):
        """Test 'from . import name' relative import."""
        detector = ImportDetector()
        code = "from . import utils"
        tree = ast.parse(code)

        # Create temp directory structure for testing
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create package structure:
            # tmpdir/
            #   __init__.py
            #   main.py (current file)
            #   utils.py (target)
            pkg_dir = Path(tmpdir)
            (pkg_dir / "__init__.py").touch()
            current_file = pkg_dir / "main.py"
            utils_file = pkg_dir / "utils.py"
            utils_file.touch()

            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, str(current_file), tree))

            assert len(relationships) == 1
            rel = relationships[0]
            assert rel.relationship_type == RelationshipType.IMPORT
            assert rel.target_symbol == "utils"
            assert rel.metadata["relative_level"] == "1"
            # Should resolve to utils.py
            assert rel.target_file == str(utils_file)

    def test_relative_import_double_dot(self):
        """Test 'from .. import name' relative import (parent directory)."""
        detector = ImportDetector()
        code = "from .. import config"
        tree = ast.parse(code)

        # Create package structure:
        # tmpdir/
        #   __init__.py
        #   config.py (target)
        #   subpkg/
        #     __init__.py
        #     main.py (current file)
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir)
            (pkg_dir / "__init__.py").touch()
            config_file = pkg_dir / "config.py"
            config_file.touch()

            subpkg_dir = pkg_dir / "subpkg"
            subpkg_dir.mkdir()
            (subpkg_dir / "__init__.py").touch()
            current_file = subpkg_dir / "main.py"

            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, str(current_file), tree))

            assert len(relationships) == 1
            rel = relationships[0]
            assert rel.metadata["relative_level"] == "2"
            # Should resolve to config.py
            assert rel.target_file == str(config_file)

    def test_relative_import_with_module(self):
        """Test 'from ..sibling import name' relative import."""
        detector = ImportDetector()
        code = "from ..utils import helper"
        tree = ast.parse(code)

        # Create package structure:
        # tmpdir/
        #   __init__.py
        #   utils/
        #     __init__.py
        #     helper.py (or helper function in __init__.py)
        #   subpkg/
        #     __init__.py
        #     main.py (current file)
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir)
            (pkg_dir / "__init__.py").touch()

            utils_dir = pkg_dir / "utils"
            utils_dir.mkdir()
            utils_init = utils_dir / "__init__.py"
            utils_init.touch()

            subpkg_dir = pkg_dir / "subpkg"
            subpkg_dir.mkdir()
            (subpkg_dir / "__init__.py").touch()
            current_file = subpkg_dir / "main.py"

            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, str(current_file), tree))

            assert len(relationships) == 1
            rel = relationships[0]
            assert rel.metadata["relative_level"] == "2"
            assert rel.metadata["module_name"] == "utils"
            # Should resolve to utils/__init__.py
            assert rel.target_file == str(utils_init)

    def test_relative_import_no_module_name(self):
        """Test 'from . import' with no module name."""
        detector = ImportDetector()
        code = "from . import *"
        tree = ast.parse(code)

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir)
            init_file = pkg_dir / "__init__.py"
            init_file.touch()
            current_file = pkg_dir / "main.py"

            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, str(current_file), tree))

            assert len(relationships) == 1
            rel = relationships[0]
            # Should resolve to __init__.py
            assert rel.target_file == str(init_file)


class TestModuleResolution:
    """Tests for module resolution to file paths."""

    def test_stdlib_module_resolution(self):
        """Test that stdlib modules are marked with <stdlib:...>."""
        detector = ImportDetector()
        stdlib_modules = ["os", "sys", "json", "pathlib", "typing", "ast"]

        for module in stdlib_modules:
            code = f"import {module}"
            tree = ast.parse(code)

            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, "/test/file.py", tree))

            assert len(relationships) == 1
            assert relationships[0].target_file == f"<stdlib:{module}>"

    def test_third_party_module_resolution(self):
        """Test that third-party modules are marked correctly.

        Note: Modules are only marked as <third-party:...> if they are actually
        installed. If not installed, they are marked as <unresolved:...>.
        This test verifies the conservative behavior.
        """
        detector = ImportDetector()
        # Common third-party packages that are not stdlib and not installed
        third_party_modules = ["requests", "flask", "django", "numpy", "pandas"]

        for module in third_party_modules:
            code = f"import {module}"
            tree = ast.parse(code)

            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, "/test/file.py", tree))

            assert len(relationships) == 1
            # If not installed, should be marked as unresolved
            # (conservative approach to avoid false positives)
            target = relationships[0].target_file
            assert target.startswith("<unresolved:") or target.startswith("<third-party:")

    def test_project_local_module_same_directory(self):
        """Test resolution of project-local module in same directory."""
        detector = ImportDetector()
        code = "import utils"
        tree = ast.parse(code)

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir)
            current_file = pkg_dir / "main.py"
            utils_file = pkg_dir / "utils.py"
            utils_file.touch()

            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, str(current_file), tree))

            assert len(relationships) == 1
            rel = relationships[0]
            # Should resolve to utils.py
            assert rel.target_file == str(utils_file)

    def test_project_local_package_same_directory(self):
        """Test resolution of project-local package in same directory."""
        detector = ImportDetector()
        code = "import utils"
        tree = ast.parse(code)

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir)
            current_file = pkg_dir / "main.py"

            # Create utils package (directory with __init__.py)
            utils_dir = pkg_dir / "utils"
            utils_dir.mkdir()
            utils_init = utils_dir / "__init__.py"
            utils_init.touch()

            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, str(current_file), tree))

            assert len(relationships) == 1
            rel = relationships[0]
            # Should resolve to utils/__init__.py
            assert rel.target_file == str(utils_init)

    def test_module_file_shadows_package(self):
        """Test that utils.py takes precedence over utils/__init__.py (TDD 3.5.2.1)."""
        detector = ImportDetector()
        code = "import utils"
        tree = ast.parse(code)

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir)
            current_file = pkg_dir / "main.py"

            # Create both utils.py and utils/__init__.py
            utils_file = pkg_dir / "utils.py"
            utils_file.touch()

            utils_dir = pkg_dir / "utils"
            utils_dir.mkdir()
            utils_init = utils_dir / "__init__.py"
            utils_init.touch()

            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, str(current_file), tree))

            assert len(relationships) == 1
            rel = relationships[0]
            # Should resolve to utils.py (higher priority)
            assert rel.target_file == str(utils_file)
            assert rel.target_file != str(utils_init)

    def test_nested_package_import(self):
        """Test resolution of nested package import (foo.bar)."""
        detector = ImportDetector()
        code = "import foo.bar"
        tree = ast.parse(code)

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir)
            current_file = pkg_dir / "main.py"

            # Create foo/bar.py structure
            foo_dir = pkg_dir / "foo"
            foo_dir.mkdir()
            (foo_dir / "__init__.py").touch()
            bar_file = foo_dir / "bar.py"
            bar_file.touch()

            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, str(current_file), tree))

            assert len(relationships) == 1
            rel = relationships[0]
            # Should resolve to foo/bar.py
            assert rel.target_file == str(bar_file)

    def test_unresolved_import(self):
        """Test that unresolved imports are marked with <unresolved:...>."""
        detector = ImportDetector()
        code = "import nonexistent_module"
        tree = ast.parse(code)

        # Use temp directory with no modules
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir)
            current_file = pkg_dir / "main.py"

            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, str(current_file), tree))

            assert len(relationships) == 1
            rel = relationships[0]
            assert rel.target_file == "<unresolved:nonexistent_module>"


class TestAliasedImports:
    """Tests for aliased imports (import as, from...import as)."""

    def test_import_as(self):
        """Test 'import module as alias' statement."""
        detector = ImportDetector()
        code = "import numpy as np"
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert len(relationships) == 1
        rel = relationships[0]
        # numpy is not installed in test environment, so it's unresolved
        assert rel.target_file.startswith("<unresolved:") or rel.target_file.startswith(
            "<third-party:"
        )
        assert rel.metadata["import_style"] == "import_as"
        assert rel.target_symbol == "numpy as np"

    def test_from_import_as(self):
        """Test 'from module import name as alias' statement."""
        detector = ImportDetector()
        code = "from os import path as ospath"
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.target_file == "<stdlib:os>"
        assert rel.metadata["import_style"] == "from_import_as"
        assert rel.target_symbol == "path as ospath"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_wildcard_import(self):
        """Test 'from module import *' statement."""
        detector = ImportDetector()
        code = "from os import *"
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.target_file == "<stdlib:os>"
        assert rel.target_symbol == "*"

    def test_relative_import_exceeds_package_depth(self):
        """Test relative import that exceeds package depth (edge case)."""
        detector = ImportDetector()
        code = "from .... import foo"  # 4 levels up
        tree = ast.parse(code)

        # Only create 2 levels of packages
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir)
            (pkg_dir / "__init__.py").touch()

            subpkg1 = pkg_dir / "sub1"
            subpkg1.mkdir()
            (subpkg1 / "__init__.py").touch()

            current_file = subpkg1 / "main.py"

            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, str(current_file), tree))

            assert len(relationships) == 1
            rel = relationships[0]
            # Should be marked as unresolved (exceeds depth)
            assert rel.target_file.startswith("<unresolved:")

    def test_multiple_import_statements(self):
        """Test file with multiple different import statements."""
        detector = ImportDetector()
        code = """
import os
import sys
from typing import List
from pathlib import Path
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have 4 relationships (one per import statement)
        assert len(relationships) == 4

        # Check each import is detected
        modules = {rel.metadata["module_name"] for rel in relationships}
        assert "os" in modules
        assert "sys" in modules
        assert "typing" in modules
        assert "pathlib" in modules
