# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Unit tests for RelationshipBuilder (Issue #122).

Tests the relationship builder component that converts FileSymbolData
into Relationships by resolving cross-file references.
"""

import time

from xfile_context.models import (
    FileSymbolData,
    ReferenceType,
    RelationshipType,
    SymbolDefinition,
    SymbolReference,
    SymbolType,
)
from xfile_context.relationship_builder import RelationshipBuilder


class TestRelationshipBuilderBasics:
    """Basic tests for RelationshipBuilder."""

    def test_initialization(self):
        """Test builder initialization."""
        builder = RelationshipBuilder()
        assert builder._file_data == {}
        assert builder._definition_index == {}

    def test_add_file_data(self):
        """Test adding file data to builder."""
        builder = RelationshipBuilder()
        data = FileSymbolData(
            filepath="/test.py",
            definitions=[],
            references=[],
            parse_time=time.time(),
        )
        builder.add_file_data(data)
        assert "/test.py" in builder._file_data

    def test_get_file_data(self):
        """Test retrieving file data."""
        builder = RelationshipBuilder()
        data = FileSymbolData(
            filepath="/test.py",
            definitions=[],
            references=[],
            parse_time=time.time(),
        )
        builder.add_file_data(data)

        result = builder.get_file_data("/test.py")
        assert result is not None
        assert result.filepath == "/test.py"

    def test_get_file_data_not_found(self):
        """Test retrieving non-existent file data."""
        builder = RelationshipBuilder()
        result = builder.get_file_data("/nonexistent.py")
        assert result is None

    def test_remove_file_data(self):
        """Test removing file data."""
        builder = RelationshipBuilder()
        data = FileSymbolData(
            filepath="/test.py",
            definitions=[],
            references=[],
            parse_time=time.time(),
        )
        builder.add_file_data(data)
        builder.remove_file_data("/test.py")

        assert builder.get_file_data("/test.py") is None

    def test_remove_file_data_not_found(self):
        """Test removing non-existent file data doesn't error."""
        builder = RelationshipBuilder()
        builder.remove_file_data("/nonexistent.py")  # Should not raise

    def test_clear(self):
        """Test clearing all data."""
        builder = RelationshipBuilder()
        data1 = FileSymbolData(
            filepath="/test1.py", definitions=[], references=[], parse_time=time.time()
        )
        data2 = FileSymbolData(
            filepath="/test2.py", definitions=[], references=[], parse_time=time.time()
        )
        builder.add_file_data(data1)
        builder.add_file_data(data2)

        builder.clear()

        assert builder.get_file_data("/test1.py") is None
        assert builder.get_file_data("/test2.py") is None


class TestDefinitionIndexing:
    """Tests for definition indexing."""

    def test_definition_indexed(self):
        """Test that definitions are indexed by name."""
        builder = RelationshipBuilder()
        func = SymbolDefinition(
            name="my_function",
            symbol_type=SymbolType.FUNCTION,
            line_start=1,
            line_end=10,
        )
        data = FileSymbolData(
            filepath="/test.py",
            definitions=[func],
            references=[],
            parse_time=time.time(),
        )
        builder.add_file_data(data)

        assert "my_function" in builder._definition_index
        assert len(builder._definition_index["my_function"]) == 1

    def test_multiple_files_same_name(self):
        """Test same symbol name defined in multiple files."""
        builder = RelationshipBuilder()

        func1 = SymbolDefinition(
            name="process", symbol_type=SymbolType.FUNCTION, line_start=1, line_end=5
        )
        func2 = SymbolDefinition(
            name="process", symbol_type=SymbolType.FUNCTION, line_start=1, line_end=10
        )

        data1 = FileSymbolData(
            filepath="/file1.py",
            definitions=[func1],
            references=[],
            parse_time=time.time(),
        )
        data2 = FileSymbolData(
            filepath="/file2.py",
            definitions=[func2],
            references=[],
            parse_time=time.time(),
        )

        builder.add_file_data(data1)
        builder.add_file_data(data2)

        # Both definitions should be in the index
        assert len(builder._definition_index["process"]) == 2

    def test_definition_removed_on_file_removal(self):
        """Test that definitions are removed from index when file is removed."""
        builder = RelationshipBuilder()
        func = SymbolDefinition(
            name="my_func", symbol_type=SymbolType.FUNCTION, line_start=1, line_end=5
        )
        data = FileSymbolData(
            filepath="/test.py",
            definitions=[func],
            references=[],
            parse_time=time.time(),
        )
        builder.add_file_data(data)
        builder.remove_file_data("/test.py")

        assert "my_func" not in builder._definition_index

    def test_lookup_definition(self):
        """Test looking up a definition."""
        builder = RelationshipBuilder()
        func = SymbolDefinition(
            name="helper",
            symbol_type=SymbolType.FUNCTION,
            line_start=10,
            line_end=20,
            signature="def helper():",
        )
        data = FileSymbolData(
            filepath="/utils.py",
            definitions=[func],
            references=[],
            parse_time=time.time(),
        )
        builder.add_file_data(data)

        result = builder.lookup_definition("helper")
        assert result is not None
        assert result.name == "helper"
        assert result.signature == "def helper():"

    def test_lookup_definition_in_specific_file(self):
        """Test looking up a definition in a specific file."""
        builder = RelationshipBuilder()

        func1 = SymbolDefinition(
            name="process", symbol_type=SymbolType.FUNCTION, line_start=1, line_end=5
        )
        func2 = SymbolDefinition(
            name="process", symbol_type=SymbolType.FUNCTION, line_start=10, line_end=20
        )

        data1 = FileSymbolData(
            filepath="/file1.py",
            definitions=[func1],
            references=[],
            parse_time=time.time(),
        )
        data2 = FileSymbolData(
            filepath="/file2.py",
            definitions=[func2],
            references=[],
            parse_time=time.time(),
        )

        builder.add_file_data(data1)
        builder.add_file_data(data2)

        result = builder.lookup_definition("process", "/file2.py")
        assert result is not None
        assert result.line_start == 10

    def test_get_all_definitions_for_symbol(self):
        """Test getting all definitions for a symbol name."""
        builder = RelationshipBuilder()

        func1 = SymbolDefinition(
            name="helper", symbol_type=SymbolType.FUNCTION, line_start=1, line_end=5
        )
        func2 = SymbolDefinition(
            name="helper", symbol_type=SymbolType.FUNCTION, line_start=10, line_end=15
        )

        data1 = FileSymbolData(
            filepath="/utils1.py",
            definitions=[func1],
            references=[],
            parse_time=time.time(),
        )
        data2 = FileSymbolData(
            filepath="/utils2.py",
            definitions=[func2],
            references=[],
            parse_time=time.time(),
        )

        builder.add_file_data(data1)
        builder.add_file_data(data2)

        definitions = builder.get_all_definitions_for_symbol("helper")
        assert len(definitions) == 2


class TestRelationshipBuilding:
    """Tests for building relationships from symbol data."""

    def test_build_import_relationship(self):
        """Test building an import relationship."""
        builder = RelationshipBuilder()

        # Target file with definition
        target_def = SymbolDefinition(
            name="helper", symbol_type=SymbolType.FUNCTION, line_start=5, line_end=15
        )
        target_data = FileSymbolData(
            filepath="/utils.py",
            definitions=[target_def],
            references=[],
            parse_time=time.time(),
        )

        # Source file with import reference
        import_ref = SymbolReference(
            name="helper",
            reference_type=ReferenceType.IMPORT,
            line_number=1,
            resolved_module="/utils.py",
            resolved_symbol="helper",
        )
        source_data = FileSymbolData(
            filepath="/main.py",
            definitions=[],
            references=[import_ref],
            parse_time=time.time(),
        )

        builder.add_file_data(target_data)
        builder.add_file_data(source_data)

        relationships = builder.build_relationships_for_file("/main.py")

        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.source_file == "/main.py"
        assert rel.target_file == "/utils.py"
        assert rel.relationship_type == RelationshipType.IMPORT
        assert rel.line_number == 1
        assert rel.target_line == 5  # Line where helper is defined

    def test_build_function_call_relationship(self):
        """Test building a function call relationship."""
        builder = RelationshipBuilder()

        # Target file with definition
        target_def = SymbolDefinition(
            name="process_data",
            symbol_type=SymbolType.FUNCTION,
            line_start=10,
            line_end=30,
        )
        target_data = FileSymbolData(
            filepath="/processor.py",
            definitions=[target_def],
            references=[],
            parse_time=time.time(),
        )

        # Source file with function call reference
        call_ref = SymbolReference(
            name="process_data",
            reference_type=ReferenceType.FUNCTION_CALL,
            line_number=25,
            resolved_module="/processor.py",
            resolved_symbol="process_data",
            caller_context="main",
        )
        source_data = FileSymbolData(
            filepath="/main.py",
            definitions=[],
            references=[call_ref],
            parse_time=time.time(),
        )

        builder.add_file_data(target_data)
        builder.add_file_data(source_data)

        relationships = builder.build_relationships_for_file("/main.py")

        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.relationship_type == RelationshipType.FUNCTION_CALL
        assert rel.target_line == 10
        assert rel.source_symbol == "main"

    def test_build_class_inheritance_relationship(self):
        """Test building a class inheritance relationship."""
        builder = RelationshipBuilder()

        # Base class file
        base_def = SymbolDefinition(
            name="BaseClass", symbol_type=SymbolType.CLASS, line_start=1, line_end=50
        )
        base_data = FileSymbolData(
            filepath="/base.py",
            definitions=[base_def],
            references=[],
            parse_time=time.time(),
        )

        # Derived class file
        class_ref = SymbolReference(
            name="BaseClass",
            reference_type=ReferenceType.CLASS_REFERENCE,
            line_number=5,
            resolved_module="/base.py",
            resolved_symbol="BaseClass",
            metadata={"child_class": "DerivedClass"},
        )
        derived_data = FileSymbolData(
            filepath="/derived.py",
            definitions=[],
            references=[class_ref],
            parse_time=time.time(),
        )

        builder.add_file_data(base_data)
        builder.add_file_data(derived_data)

        relationships = builder.build_relationships_for_file("/derived.py")

        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.relationship_type == RelationshipType.CLASS_INHERITANCE
        assert rel.target_file == "/base.py"
        assert rel.target_line == 1

    def test_build_all_relationships(self):
        """Test building relationships for all files."""
        builder = RelationshipBuilder()

        # File A imports from B
        ref_a = SymbolReference(
            name="foo",
            reference_type=ReferenceType.IMPORT,
            line_number=1,
            resolved_module="/file_b.py",
            resolved_symbol="foo",
        )
        data_a = FileSymbolData(
            filepath="/file_a.py",
            definitions=[],
            references=[ref_a],
            parse_time=time.time(),
        )

        # File B imports from A
        ref_b = SymbolReference(
            name="bar",
            reference_type=ReferenceType.IMPORT,
            line_number=1,
            resolved_module="/file_a.py",
            resolved_symbol="bar",
        )
        data_b = FileSymbolData(
            filepath="/file_b.py",
            definitions=[],
            references=[ref_b],
            parse_time=time.time(),
        )

        builder.add_file_data(data_a)
        builder.add_file_data(data_b)

        all_relationships = builder.build_relationships()

        assert len(all_relationships) == 2

    def test_unresolved_reference(self):
        """Test building relationship for unresolved reference."""
        builder = RelationshipBuilder()

        ref = SymbolReference(
            name="unknown_func",
            reference_type=ReferenceType.FUNCTION_CALL,
            line_number=10,
            # resolved_module is None
        )
        data = FileSymbolData(
            filepath="/main.py",
            definitions=[],
            references=[ref],
            parse_time=time.time(),
        )

        builder.add_file_data(data)
        relationships = builder.build_relationships_for_file("/main.py")

        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.target_file == "<unresolved:unknown_func>"

    def test_stdlib_reference(self):
        """Test building relationship for stdlib reference."""
        builder = RelationshipBuilder()

        ref = SymbolReference(
            name="os",
            reference_type=ReferenceType.IMPORT,
            line_number=1,
            resolved_module="<stdlib:os>",
            resolved_symbol="os",
        )
        data = FileSymbolData(
            filepath="/main.py",
            definitions=[],
            references=[ref],
            parse_time=time.time(),
        )

        builder.add_file_data(data)
        relationships = builder.build_relationships_for_file("/main.py")

        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.target_file == "<stdlib:os>"
        assert rel.target_line is None  # No target line for stdlib

    def test_preserves_metadata(self):
        """Test that reference metadata is preserved in relationship."""
        builder = RelationshipBuilder()

        ref = SymbolReference(
            name="helper",
            reference_type=ReferenceType.FUNCTION_CALL,
            line_number=10,
            resolved_module="/utils.py",
            resolved_symbol="helper",
            metadata={"call_pattern": "simple", "custom_key": "custom_value"},
        )
        data = FileSymbolData(
            filepath="/main.py",
            definitions=[],
            references=[ref],
            parse_time=time.time(),
        )

        builder.add_file_data(data)
        relationships = builder.build_relationships_for_file("/main.py")

        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.metadata["call_pattern"] == "simple"
        assert rel.metadata["custom_key"] == "custom_value"
