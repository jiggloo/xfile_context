# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for WildcardImportDetector plugin.

Tests cover:
- Wildcard import detection (from module import *)
- Module-level tracking
- Wildcard metadata marking
- Warning configuration (warn_on_wildcards)
- Edge cases
"""

import ast
import logging

from xfile_context.detectors import WildcardImportDetector
from xfile_context.models import RelationshipType


class TestWildcardImportDetectorBasics:
    """Tests for basic wildcard import detector functionality."""

    def test_detector_name(self):
        """Test detector name is 'WildcardImportDetector'."""
        detector = WildcardImportDetector()
        assert detector.name() == "WildcardImportDetector"

    def test_detector_priority(self):
        """Test detector has priority 90 (after ConditionalImportDetector)."""
        detector = WildcardImportDetector()
        assert detector.priority() == 90

    def test_no_wildcards_returns_empty_list(self):
        """Test that code with no wildcard imports returns empty relationship list."""
        detector = WildcardImportDetector()
        code = """
import os
from typing import List
x = 1
"""
        tree = ast.parse(code)
        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert relationships == []

    def test_regular_from_import_not_detected(self):
        """Test that regular from imports are not detected as wildcards."""
        detector = WildcardImportDetector()
        code = """
from os import path
from typing import List, Dict
"""
        tree = ast.parse(code)
        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert relationships == []

    def test_import_statement_not_detected(self):
        """Test that regular import statements are not detected as wildcards."""
        detector = WildcardImportDetector()
        code = """
import os
import sys
"""
        tree = ast.parse(code)
        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert relationships == []


class TestWildcardImportDetection:
    """Tests for wildcard import detection."""

    def test_wildcard_import_stdlib(self):
        """Test detection of 'from os import *' pattern (stdlib module)."""
        detector = WildcardImportDetector()
        code = """
from os import *
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have 1 wildcard import relationship
        assert len(relationships) == 1
        rel = relationships[0]

        assert rel.relationship_type == RelationshipType.IMPORT
        assert rel.source_file == "/test/file.py"
        assert rel.target_file == "<stdlib:os>"
        assert rel.target_symbol == "os"
        assert rel.metadata["wildcard"] == "true"
        assert "Cannot track which specific names" in rel.metadata["limitation"]

    def test_wildcard_import_third_party(self):
        """Test detection of wildcard import from third-party module."""
        detector = WildcardImportDetector()
        code = """
from django.contrib import *
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert len(relationships) == 1
        rel = relationships[0]

        assert rel.relationship_type == RelationshipType.IMPORT
        # Third-party modules that aren't in project are marked as unresolved
        assert rel.target_file == "<unresolved:django.contrib>"
        assert rel.target_symbol == "django.contrib"
        assert rel.metadata["wildcard"] == "true"

    def test_wildcard_import_relative(self):
        """Test detection of relative wildcard import."""
        detector = WildcardImportDetector()
        code = """
from . import *
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert len(relationships) == 1
        rel = relationships[0]

        assert rel.relationship_type == RelationshipType.IMPORT
        assert rel.metadata["wildcard"] == "true"

    def test_wildcard_import_parent_relative(self):
        """Test detection of parent-relative wildcard import."""
        detector = WildcardImportDetector()
        code = """
from .. import *
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert len(relationships) == 1
        rel = relationships[0]

        assert rel.relationship_type == RelationshipType.IMPORT
        assert rel.metadata["wildcard"] == "true"

    def test_multiple_wildcard_imports(self):
        """Test multiple wildcard imports in same file."""
        detector = WildcardImportDetector()
        code = """
from os import *
from sys import *
from typing import *
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have 3 wildcard import relationships
        assert len(relationships) == 3

        # Check all are marked as wildcard
        for rel in relationships:
            assert rel.relationship_type == RelationshipType.IMPORT
            assert rel.metadata["wildcard"] == "true"

        # Check imported modules
        imported_modules = {rel.target_symbol for rel in relationships}
        assert imported_modules == {"os", "sys", "typing"}


class TestWildcardWarningConfiguration:
    """Tests for warn_on_wildcards configuration."""

    def test_warning_disabled_by_default(self, caplog):
        """Test that warnings are disabled by default (warn_on_wildcards=False)."""
        detector = WildcardImportDetector()
        code = """
from os import *
"""
        tree = ast.parse(code)

        with caplog.at_level(logging.WARNING):
            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should detect the wildcard import
        assert len(relationships) == 1

        # Should not emit warning (default behavior per PRD 2.5)
        assert not any("Wildcard import detected" in record.message for record in caplog.records)

    def test_warning_enabled_explicitly(self, caplog):
        """Test that warnings are emitted when warn_on_wildcards=True."""
        detector = WildcardImportDetector(warn_on_wildcards=True)
        code = """
from os import *
"""
        tree = ast.parse(code)

        with caplog.at_level(logging.WARNING):
            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should detect the wildcard import
        assert len(relationships) == 1

        # Should emit warning with EC-4 reference
        warning_found = False
        for record in caplog.records:
            if "Wildcard import detected" in record.message and "EC-4" in record.message:
                assert "/test/file.py" in record.message
                assert "from os import *" in record.message
                warning_found = True
                break

        assert warning_found, "Expected wildcard import warning not found in logs"

    def test_warning_includes_line_number(self, caplog):
        """Test that warning includes line number."""
        detector = WildcardImportDetector(warn_on_wildcards=True)
        code = """# Line 1
# Line 2
from os import *  # Line 3
"""
        tree = ast.parse(code)

        with caplog.at_level(logging.WARNING):
            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have warning with line number 3
        warning_found = False
        for record in caplog.records:
            if "Wildcard import detected" in record.message:
                # Line number should be in format "file.py:3"
                assert ":3:" in record.message or "line 3" in record.message.lower()
                warning_found = True
                break

        assert warning_found

    def test_warning_for_relative_import(self, caplog):
        """Test warning message for relative wildcard import."""
        detector = WildcardImportDetector(warn_on_wildcards=True)
        code = """
from . import *
"""
        tree = ast.parse(code)

        with caplog.at_level(logging.WARNING):
            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should emit warning mentioning relative import
        warning_found = False
        for record in caplog.records:
            if "Wildcard import detected" in record.message:
                # Should mention relative import
                assert "from" in record.message and "import *" in record.message
                warning_found = True
                break

        assert warning_found


class TestWildcardMetadata:
    """Tests for wildcard import metadata."""

    def test_metadata_includes_wildcard_flag(self):
        """Test that metadata includes wildcard=true flag."""
        detector = WildcardImportDetector()
        code = """
from os import *
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert len(relationships) == 1
        assert relationships[0].metadata["wildcard"] == "true"

    def test_metadata_includes_limitation_message(self):
        """Test that metadata includes limitation explanation."""
        detector = WildcardImportDetector()
        code = """
from os import *
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert len(relationships) == 1
        limitation = relationships[0].metadata["limitation"]
        assert "Cannot track which specific names" in limitation
        assert "imported" in limitation.lower()

    def test_metadata_all_string_values(self):
        """Test that all metadata values are strings (per metadata type requirement)."""
        detector = WildcardImportDetector()
        code = """
from os import *
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert len(relationships) == 1
        rel = relationships[0]

        # All metadata values must be strings
        for key, value in rel.metadata.items():
            assert isinstance(
                value, str
            ), f"Metadata key '{key}' has non-string value: {type(value)}"


class TestWildcardEdgeCases:
    """Tests for edge cases and error handling."""

    def test_wildcard_with_other_imports(self):
        """Test wildcard import mixed with regular imports."""
        detector = WildcardImportDetector()
        code = """
import os
from sys import path
from typing import *
from collections import defaultdict
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should only detect the wildcard import
        assert len(relationships) == 1
        assert relationships[0].target_symbol == "typing"
        assert relationships[0].metadata["wildcard"] == "true"

    def test_wildcard_in_function(self):
        """Test wildcard import inside function (not module level)."""
        detector = WildcardImportDetector()
        code = """
def foo():
    from os import *
    return path
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should still detect the wildcard import
        # (even though it's not at module level, it's still an import)
        assert len(relationships) == 1
        assert relationships[0].metadata["wildcard"] == "true"

    def test_wildcard_in_conditional(self):
        """Test wildcard import in conditional block."""
        detector = WildcardImportDetector()
        code = """
if True:
    from os import *
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should detect the wildcard import
        assert len(relationships) == 1
        assert relationships[0].metadata["wildcard"] == "true"

    def test_empty_file(self):
        """Test empty file produces no relationships."""
        detector = WildcardImportDetector()
        code = ""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert relationships == []

    def test_comments_only(self):
        """Test file with only comments produces no relationships."""
        detector = WildcardImportDetector()
        code = """
# This is a comment
# Another comment
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        assert relationships == []
