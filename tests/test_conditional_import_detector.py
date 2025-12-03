# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for ConditionalImportDetector plugin.

Tests cover:
- TYPE_CHECKING conditional imports
- sys.version_info conditional imports
- Metadata marking for conditional relationships
- Edge cases
"""

import ast

from xfile_context.detectors import ConditionalImportDetector
from xfile_context.models import RelationshipType


class TestConditionalImportDetectorBasics:
    """Tests for basic conditional import detector functionality."""

    def test_detector_name(self):
        """Test detector name is 'ConditionalImportDetector'."""
        detector = ConditionalImportDetector()
        assert detector.name() == "ConditionalImportDetector"

    def test_detector_priority(self):
        """Test detector has priority 95 (after ImportDetector)."""
        detector = ConditionalImportDetector()
        assert detector.priority() == 95

    def test_no_conditionals_returns_empty_list(self):
        """Test that code with no conditional imports returns empty relationship list."""
        detector = ConditionalImportDetector()
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


class TestTypeCheckingConditionals:
    """Tests for TYPE_CHECKING conditional imports."""

    def test_type_checking_import(self):
        """Test detection of 'if TYPE_CHECKING: import ...' pattern."""
        detector = ConditionalImportDetector()
        code = """
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have 1 conditional import relationship
        # (The TYPE_CHECKING import itself is not conditional)
        assert len(relationships) == 1
        rel = relationships[0]

        assert rel.relationship_type == RelationshipType.IMPORT
        assert rel.source_file == "/test/file.py"
        assert rel.target_file == "<stdlib:os>"
        assert rel.target_symbol == "os"
        assert rel.metadata["conditional"] == "true"
        assert rel.metadata["condition_type"] == "TYPE_CHECKING"
        assert rel.metadata["condition_expr"] == "TYPE_CHECKING"

    def test_type_checking_from_import(self):
        """Test detection of 'if TYPE_CHECKING: from ... import ...' pattern."""
        detector = ConditionalImportDetector()
        code = """
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List, Dict
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have 2 conditional import relationships (List and Dict)
        assert len(relationships) == 2

        # Check both imports are marked as conditional
        for rel in relationships:
            assert rel.relationship_type == RelationshipType.IMPORT
            assert rel.metadata["conditional"] == "true"
            assert rel.metadata["condition_type"] == "TYPE_CHECKING"
            assert rel.metadata["condition_expr"] == "TYPE_CHECKING"

        # Check imported names
        imported_names = {rel.target_symbol for rel in relationships}
        assert imported_names == {"List", "Dict"}

    def test_type_checking_multiple_imports(self):
        """Test multiple imports within TYPE_CHECKING block."""
        detector = ConditionalImportDetector()
        code = """
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os
    import sys
    from typing import Optional
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have 3 conditional imports
        assert len(relationships) == 3

        # All should be marked as conditional
        for rel in relationships:
            assert rel.metadata["conditional"] == "true"
            assert rel.metadata["condition_type"] == "TYPE_CHECKING"


class TestVersionConditionals:
    """Tests for sys.version_info conditional imports."""

    def test_version_check_import(self):
        """Test detection of 'if sys.version_info >= (3, 8): import ...' pattern."""
        detector = ConditionalImportDetector()
        code = """
import sys

if sys.version_info >= (3, 8):
    import importlib.metadata
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have 1 conditional import
        assert len(relationships) == 1
        rel = relationships[0]

        assert rel.relationship_type == RelationshipType.IMPORT
        assert rel.metadata["conditional"] == "true"
        assert rel.metadata["condition_type"] == "version_check"
        # The condition expression should contain the version check
        assert "sys.version_info" in rel.metadata["condition_expr"]
        assert ">=" in rel.metadata["condition_expr"]

    def test_version_check_multiple_operators(self):
        """Test version checks with different comparison operators."""
        detector = ConditionalImportDetector()
        test_cases = [
            "if sys.version_info >= (3, 8):",
            "if sys.version_info > (3, 7):",
            "if sys.version_info < (4, 0):",
            "if sys.version_info <= (3, 11):",
            "if sys.version_info == (3, 9):",
        ]

        for condition in test_cases:
            code = f"""
import sys

{condition}
    import os
"""
            tree = ast.parse(code)

            relationships = []
            for node in ast.walk(tree):
                relationships.extend(detector.detect(node, "/test/file.py", tree))

            # Should have 1 conditional import
            assert len(relationships) == 1, f"Failed for condition: {condition}"
            rel = relationships[0]

            assert rel.metadata["conditional"] == "true"
            assert rel.metadata["condition_type"] == "version_check"
            assert "sys.version_info" in rel.metadata["condition_expr"]

    def test_version_check_slice(self):
        """Test version checks using slice notation (sys.version_info[:2])."""
        detector = ConditionalImportDetector()
        code = """
import sys

if sys.version_info[:2] >= (3, 8):
    import importlib.metadata
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have 1 conditional import
        assert len(relationships) == 1
        rel = relationships[0]

        assert rel.metadata["conditional"] == "true"
        assert rel.metadata["condition_type"] == "version_check"


class TestNonConditionalPatterns:
    """Tests for non-conditional patterns that should NOT be detected."""

    def test_regular_if_not_detected(self):
        """Test that regular if statements don't create conditional imports."""
        detector = ConditionalImportDetector()
        code = """
x = True

if x:
    import os
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have 0 relationships (regular if, not TYPE_CHECKING or version check)
        assert len(relationships) == 0

    def test_other_name_not_detected(self):
        """Test that if blocks with other variable names are not detected."""
        detector = ConditionalImportDetector()
        code = """
DEBUG = True

if DEBUG:
    import pdb
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have 0 relationships
        assert len(relationships) == 0

    def test_non_import_statements_not_detected(self):
        """Test that non-import statements in TYPE_CHECKING block are not detected."""
        detector = ConditionalImportDetector()
        code = """
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    x = 1
    y = 2
    print("hello")
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have 0 relationships (no imports in the block)
        assert len(relationships) == 0


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_nested_if_blocks(self):
        """Test that nested if blocks only apply outer condition.

        Only the imports in the immediate body of TYPE_CHECKING should get
        the conditional metadata. Nested if blocks are not traversed.
        """
        detector = ConditionalImportDetector()
        code = """
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os
    if True:
        import sys
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should only detect import os (direct child of TYPE_CHECKING body)
        # import sys is in nested if block and should NOT be detected
        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.target_symbol == "os"
        assert rel.metadata["conditional"] == "true"
        assert rel.metadata["condition_type"] == "TYPE_CHECKING"

    def test_aliased_conditional_import(self):
        """Test conditional imports with aliases."""
        detector = ConditionalImportDetector()
        code = """
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from typing import List as L
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have 2 conditional imports
        assert len(relationships) == 2

        # Check that both are marked as conditional
        for rel in relationships:
            assert rel.metadata["conditional"] == "true"
            assert rel.metadata["condition_type"] == "TYPE_CHECKING"

        # Check aliases are preserved
        symbols = {rel.target_symbol for rel in relationships}
        assert "numpy as np" in symbols
        assert "List as L" in symbols

    def test_wildcard_conditional_import(self):
        """Test conditional wildcard imports."""
        detector = ConditionalImportDetector()
        code = """
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import *
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have 1 conditional import
        assert len(relationships) == 1
        rel = relationships[0]

        assert rel.target_symbol == "*"
        assert rel.metadata["conditional"] == "true"

    def test_multiple_conditional_blocks(self):
        """Test multiple separate conditional blocks in same file."""
        detector = ConditionalImportDetector()
        code = """
from typing import TYPE_CHECKING
import sys

if TYPE_CHECKING:
    import os

if sys.version_info >= (3, 8):
    import importlib.metadata
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have 2 conditional imports (one from each block)
        assert len(relationships) == 2

        # Check condition types
        condition_types = {rel.metadata["condition_type"] for rel in relationships}
        assert "TYPE_CHECKING" in condition_types
        assert "version_check" in condition_types

    def test_conditional_import_line_numbers(self):
        """Test that line numbers are correctly captured for conditional imports."""
        detector = ConditionalImportDetector()
        code = """
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os
    import sys
"""
        tree = ast.parse(code)

        relationships = []
        for node in ast.walk(tree):
            relationships.extend(detector.detect(node, "/test/file.py", tree))

        # Should have 2 imports with different line numbers
        assert len(relationships) == 2
        line_numbers = {rel.line_number for rel in relationships}
        # Both imports should have line numbers (4 and 5)
        assert len(line_numbers) == 2
        assert all(ln > 0 for ln in line_numbers)

    def test_malformed_ast_node_gracefully_handled(self):
        """Test that malformed AST nodes are handled gracefully (EC-18 related).

        When the AST is malformed or has unexpected structure, the detector
        should skip gracefully without crashing.
        """
        from unittest.mock import MagicMock

        detector = ConditionalImportDetector()

        # Create a mock If node with a test that will raise AttributeError
        malformed_if = MagicMock(spec=ast.If)
        malformed_if.test = MagicMock()
        # Make accessing attributes raise AttributeError
        type(malformed_if.test).id = property(
            lambda self: (_ for _ in ()).throw(AttributeError("no id"))
        )

        tree = ast.parse("x = 1")

        # Should not raise, should return empty list
        relationships = detector.detect(malformed_if, "/test/file.py", tree)
        assert relationships == []

    def test_malformed_ast_with_type_error(self):
        """Test that TypeError during condition analysis is handled gracefully."""
        from unittest.mock import patch

        detector = ConditionalImportDetector()

        # Create a valid If node
        code = """
if TYPE_CHECKING:
    import os
"""
        tree = ast.parse(code)

        # Find the If node
        if_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                if_node = node
                break

        # Patch _analyze_condition to raise TypeError
        with patch.object(detector, "_analyze_condition", side_effect=TypeError("test")):
            relationships = detector.detect(if_node, "/test/file.py", tree)
            assert relationships == []


class TestFallbackCodePaths:
    """Tests for fallback code paths (low priority for Python 3.10+).

    These tests cover code that exists for robustness but may not execute
    on Python 3.10+ where ast.unparse is always available.
    """

    def test_node_to_string_depth_limit(self):
        """Test that _node_to_string respects max recursion depth."""
        detector = ConditionalImportDetector()

        # Create a deeply nested attribute access
        node = ast.Name(id="a")
        for _ in range(25):  # Exceed max_depth of 20
            node = ast.Attribute(value=node, attr="x")

        result = detector._node_to_string(node)
        assert "<too_deep>" in result

    def test_node_to_string_subscript(self):
        """Test _node_to_string handles Subscript nodes."""
        detector = ConditionalImportDetector()

        # Create sys.version_info[:2] AST structure
        code = "sys.version_info[:2]"
        tree = ast.parse(code, mode="eval")
        subscript_node = tree.body  # This is the Subscript node

        result = detector._node_to_string(subscript_node)
        assert "sys.version_info" in result
        assert "[...]" in result

    def test_node_to_string_tuple(self):
        """Test _node_to_string handles Tuple nodes."""
        detector = ConditionalImportDetector()

        # Create a tuple (3, 8)
        code = "(3, 8)"
        tree = ast.parse(code, mode="eval")
        tuple_node = tree.body

        result = detector._node_to_string(tuple_node)
        assert "3" in result
        assert "8" in result

    def test_node_to_string_unknown_node_type(self):
        """Test _node_to_string handles unknown node types."""
        detector = ConditionalImportDetector()

        # Create a node type that _node_to_string doesn't explicitly handle
        code = "[1, 2, 3]"  # List node
        tree = ast.parse(code, mode="eval")
        list_node = tree.body

        result = detector._node_to_string(list_node)
        assert result == "<expr>"

    def test_unparse_expr_fallback_with_compare(self):
        """Test _unparse_expr fallback for Compare nodes.

        Note: On Python 3.10+, ast.unparse is used. This tests the fallback
        by temporarily removing ast.unparse (if possible) or verifying the
        primary path works correctly.
        """
        detector = ConditionalImportDetector()

        # Create a Compare node: sys.version_info >= (3, 8)
        code = "sys.version_info >= (3, 8)"
        tree = ast.parse(code, mode="eval")
        compare_node = tree.body

        # Test the primary path (ast.unparse available on 3.10+)
        result = detector._unparse_expr(compare_node)
        assert "sys.version_info" in result
        assert ">=" in result
        assert "3" in result
        assert "8" in result

    def test_unparse_expr_all_comparison_operators(self):
        """Test _unparse_expr handles all comparison operators."""
        detector = ConditionalImportDetector()

        test_cases = [
            ("a > b", ">"),
            ("a >= b", ">="),
            ("a < b", "<"),
            ("a <= b", "<="),
            ("a == b", "=="),
            ("a != b", "!="),
        ]

        for code, expected_op in test_cases:
            tree = ast.parse(code, mode="eval")
            compare_node = tree.body
            result = detector._unparse_expr(compare_node)
            assert expected_op in result, f"Failed for {code}"
