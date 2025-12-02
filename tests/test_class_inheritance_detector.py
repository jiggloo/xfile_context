# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for ClassInheritanceDetector.

This module tests class inheritance detection and resolution according to
TDD Section 3.5.2.3 specifications.

Test Coverage:
- Single inheritance
- Multiple inheritance
- Nested inheritance (module.Parent)
- Parent class resolution order (local, imported, built-in, unresolved)
- Inheritance order tracking
"""

import ast

from xfile_context.detectors import ClassInheritanceDetector
from xfile_context.models import RelationshipType


class TestClassInheritanceDetector:
    """Tests for ClassInheritanceDetector."""

    def test_single_inheritance_local(self, tmp_path):
        """Test detection of single inheritance with local parent class."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class Parent:
    pass

class Child(Parent):
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one inheritance relationship
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.relationship_type == RelationshipType.CLASS_INHERITANCE
        assert rel.source_symbol == "Child"
        assert rel.target_symbol == "Parent"
        assert rel.target_file == str(test_file)  # Resolves to local file
        assert rel.metadata["child_class"] == "Child"
        assert rel.metadata["parent_class"] == "Parent"
        assert rel.metadata["inheritance_order"] == 0
        assert rel.metadata["total_parents"] == 1

    def test_multiple_inheritance(self, tmp_path):
        """Test detection of multiple inheritance."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class Parent1:
    pass

class Parent2:
    pass

class Child(Parent1, Parent2):
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect two inheritance relationships
        assert len(relationships) == 2

        # Check first parent
        rel1 = [r for r in relationships if r.metadata["inheritance_order"] == 0][0]
        assert rel1.source_symbol == "Child"
        assert rel1.target_symbol == "Parent1"
        assert rel1.metadata["total_parents"] == 2

        # Check second parent
        rel2 = [r for r in relationships if r.metadata["inheritance_order"] == 1][0]
        assert rel2.source_symbol == "Child"
        assert rel2.target_symbol == "Parent2"
        assert rel2.metadata["total_parents"] == 2

    def test_builtin_inheritance(self, tmp_path):
        """Test detection of inheritance from built-in classes."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class MyException(Exception):
    pass

class MyList(list):
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect two inheritance relationships
        assert len(relationships) == 2

        # Check Exception inheritance
        exc_rel = [r for r in relationships if r.source_symbol == "MyException"][0]
        assert exc_rel.target_symbol == "Exception"
        assert exc_rel.target_file == "<builtin:Exception>"

        # Check list inheritance
        list_rel = [r for r in relationships if r.source_symbol == "MyList"][0]
        assert list_rel.target_symbol == "list"
        assert list_rel.target_file == "<builtin:list>"

    def test_unresolved_parent(self, tmp_path):
        """Test detection of inheritance with unresolved parent class."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class Child(UnknownParent):
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one inheritance relationship
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.source_symbol == "Child"
        assert rel.target_symbol == "UnknownParent"
        assert rel.target_file == "<unresolved:UnknownParent>"

    def test_imported_parent_class(self, tmp_path):
        """Test resolution of inheritance from imported parent class."""
        # Create parent module
        parent_file = tmp_path / "parent.py"
        parent_file.write_text(
            """
class BaseClass:
    pass
"""
        )

        # Create child module that imports and inherits
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
from parent import BaseClass

class Child(BaseClass):
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one inheritance relationship
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.source_symbol == "Child"
        assert rel.target_symbol == "BaseClass"
        # Should resolve to parent.py
        assert rel.target_file == str(parent_file)

    def test_aliased_import_parent_class(self, tmp_path):
        """Test resolution of inheritance using aliased import."""
        # Create parent module
        parent_file = tmp_path / "parent.py"
        parent_file.write_text(
            """
class BaseClass:
    pass
"""
        )

        # Create child module with aliased import
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
from parent import BaseClass as Base

class Child(Base):
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one inheritance relationship
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.source_symbol == "Child"
        assert rel.target_symbol == "Base"
        # Should resolve to parent.py via alias tracking
        assert rel.target_file == str(parent_file)

    def test_module_qualified_parent(self, tmp_path):
        """Test detection of module-qualified parent: class Child(module.Parent)."""
        # Create parent module
        parent_file = tmp_path / "parent.py"
        parent_file.write_text(
            """
class BaseClass:
    pass
"""
        )

        # Create child module that imports module and uses qualified name
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
import parent

class Child(parent.BaseClass):
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one inheritance relationship
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.source_symbol == "Child"
        assert rel.target_symbol == "parent.BaseClass"
        assert rel.target_file == str(parent_file)

    def test_nested_module_qualified_parent(self, tmp_path):
        """Test detection of nested module-qualified parent: pkg.module.Parent."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
import pkg.module

class Child(pkg.module.Parent):
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one inheritance relationship
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.source_symbol == "Child"
        assert rel.target_symbol == "pkg.module.Parent"
        # Will be unresolved since pkg.module doesn't exist
        assert rel.target_file.startswith("<unresolved:")

    def test_stdlib_parent_class(self, tmp_path):
        """Test inheritance from stdlib classes via module qualification."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
import collections

class MyCounter(collections.Counter):
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one inheritance relationship
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.source_symbol == "MyCounter"
        assert rel.target_symbol == "collections.Counter"
        assert rel.target_file == "<stdlib:collections.Counter>"

    def test_no_inheritance(self, tmp_path):
        """Test that classes without inheritance are not detected."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class Standalone:
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should not detect any inheritance relationships
        assert len(relationships) == 0

    def test_local_class_shadows_import(self, tmp_path):
        """Test that local class definition shadows imported class."""
        # Create parent module
        parent_file = tmp_path / "parent.py"
        parent_file.write_text(
            """
class BaseClass:
    pass
"""
        )

        # Create test file where local class shadows import
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
from parent import BaseClass

class BaseClass:  # Local definition shadows import
    pass

class Child(BaseClass):
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one inheritance relationship
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.source_symbol == "Child"
        assert rel.target_symbol == "BaseClass"
        # Should resolve to local file (not parent.py)
        assert rel.target_file == str(test_file)

    def test_inheritance_chain(self, tmp_path):
        """Test detection of inheritance chain: Grandchild -> Child -> Parent."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class Parent:
    pass

class Child(Parent):
    pass

class Grandchild(Child):
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect two inheritance relationships
        assert len(relationships) == 2

        # Check Child -> Parent
        child_rel = [r for r in relationships if r.source_symbol == "Child"][0]
        assert child_rel.target_symbol == "Parent"
        assert child_rel.target_file == str(test_file)

        # Check Grandchild -> Child
        grandchild_rel = [r for r in relationships if r.source_symbol == "Grandchild"][0]
        assert grandchild_rel.target_symbol == "Child"
        assert grandchild_rel.target_file == str(test_file)

    def test_line_number_tracking(self, tmp_path):
        """Test that line numbers are correctly tracked."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class Parent:
    pass

class Child(Parent):  # Line 5
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Check line number
        assert len(relationships) == 1
        assert relationships[0].line_number == 5

    def test_relative_import_parent_class(self, tmp_path):
        """Test resolution of inheritance from relative imports."""
        # Create package structure
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")

        # Create parent module in package
        parent_file = pkg_dir / "parent.py"
        parent_file.write_text(
            """
class BaseClass:
    pass
"""
        )

        # Create child module in package with relative import
        test_file = pkg_dir / "child.py"
        test_file.write_text(
            """
from .parent import BaseClass

class Child(BaseClass):
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one inheritance relationship
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.source_symbol == "Child"
        assert rel.target_symbol == "BaseClass"
        # Should resolve to parent.py in same package
        assert rel.target_file == str(parent_file)

    def test_wildcard_import_unresolved(self, tmp_path):
        """Test that inheritance from wildcard imports is unresolved."""
        # Create parent module
        parent_file = tmp_path / "parent.py"
        parent_file.write_text(
            """
class BaseClass:
    pass
"""
        )

        # Create child module with wildcard import
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
from parent import *

class Child(BaseClass):
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one inheritance relationship, but marked as unresolved
        # (wildcard imports don't track specific names)
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.source_symbol == "Child"
        assert rel.target_symbol == "BaseClass"
        # Cannot resolve from wildcard import in v0.1.0
        assert rel.target_file == "<unresolved:BaseClass>"

    def test_detector_priority(self):
        """Test that ClassInheritanceDetector has correct priority."""
        detector = ClassInheritanceDetector()
        assert detector.priority() == 50  # Core detector priority

    def test_detector_name(self):
        """Test that ClassInheritanceDetector has correct name."""
        detector = ClassInheritanceDetector()
        assert detector.name() == "ClassInheritanceDetector"

    def test_detector_reuse_across_files(self, tmp_path):
        """Test that detector instance can be safely reused across multiple files.

        This tests the production scenario where DetectorRegistry registers a single
        detector instance and reuses it for all files in the project. The detector
        must properly invalidate its cache when switching to a different file.
        """
        # Create file1 with BaseClass definition
        file1 = tmp_path / "file1.py"
        file1.write_text(
            """
class BaseClass:
    pass

class Child(BaseClass):
    pass
"""
        )

        # Create file2 that inherits from BaseClass but doesn't define it
        file2 = tmp_path / "file2.py"
        file2.write_text(
            """
class Child(BaseClass):
    pass
"""
        )

        # Use same detector instance for both files (production pattern)
        detector = ClassInheritanceDetector()

        # Analyze file1
        tree1 = ast.parse(file1.read_text())
        file1_rels = []
        for node in ast.walk(tree1):
            rels = detector.detect(node, str(file1), tree1)
            file1_rels.extend(rels)

        # File1 should resolve BaseClass to itself
        file1_child = [r for r in file1_rels if r.source_symbol == "Child"][0]
        assert file1_child.target_file == str(file1)

        # Analyze file2 with SAME detector instance
        tree2 = ast.parse(file2.read_text())
        file2_rels = []
        for node in ast.walk(tree2):
            rels = detector.detect(node, str(file2), tree2)
            file2_rels.extend(rels)

        # File2 should mark BaseClass as unresolved (not defined in file2, not imported)
        file2_child = [r for r in file2_rels if r.source_symbol == "Child"][0]
        assert file2_child.target_file == "<unresolved:BaseClass>", (
            f"Cache pollution detected: BaseClass in file2 resolved to "
            f"{file2_child.target_file} instead of <unresolved:BaseClass>. "
            f"This indicates the detector's cache was not properly invalidated "
            f"when switching from file1 to file2."
        )

    def test_mixed_inheritance_builtin_and_custom(self, tmp_path):
        """Test multiple inheritance with both built-in and custom classes."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class CustomBase:
    pass

class Child(CustomBase, Exception):
    pass
"""
        )

        detector = ClassInheritanceDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect two inheritance relationships
        assert len(relationships) == 2

        # Check CustomBase inheritance
        custom_rel = [r for r in relationships if r.target_symbol == "CustomBase"][0]
        assert custom_rel.target_file == str(test_file)
        assert custom_rel.metadata["inheritance_order"] == 0

        # Check Exception inheritance
        exc_rel = [r for r in relationships if r.target_symbol == "Exception"][0]
        assert exc_rel.target_file == "<builtin:Exception>"
        assert exc_rel.metadata["inheritance_order"] == 1
