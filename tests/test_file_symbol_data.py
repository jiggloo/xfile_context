# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Unit tests for FileSymbolData and related models (Issue #122).

Tests the intermediate data model for AST-parsed data:
- SymbolDefinition: Function, class, and variable definitions
- SymbolReference: Import, function call, and class references
- FileSymbolData: Container for all symbols in a file
"""

import time

import pytest

from xfile_context.models import (
    FileSymbolData,
    ReferenceType,
    SymbolDefinition,
    SymbolReference,
    SymbolType,
)


class TestSymbolDefinition:
    """Tests for SymbolDefinition model."""

    @pytest.mark.extended
    def test_basic_function_definition(self):
        """Test creating a function definition."""
        defn = SymbolDefinition(
            name="my_function",
            symbol_type=SymbolType.FUNCTION,
            line_start=10,
            line_end=20,
            signature="def my_function(a, b):",
        )
        assert defn.name == "my_function"
        assert defn.symbol_type == SymbolType.FUNCTION
        assert defn.line_start == 10
        assert defn.line_end == 20
        assert defn.signature == "def my_function(a, b):"

    @pytest.mark.extended
    def test_class_definition_with_bases(self):
        """Test creating a class definition with base classes."""
        defn = SymbolDefinition(
            name="MyClass",
            symbol_type=SymbolType.CLASS,
            line_start=5,
            line_end=50,
            signature="class MyClass",
            bases=["BaseClass", "Mixin"],
            decorators=["dataclass"],
        )
        assert defn.name == "MyClass"
        assert defn.bases == ["BaseClass", "Mixin"]
        assert defn.decorators == ["dataclass"]

    @pytest.mark.extended
    def test_method_definition(self):
        """Test creating a method definition with parent class."""
        defn = SymbolDefinition(
            name="process",
            symbol_type=SymbolType.METHOD,
            line_start=15,
            line_end=25,
            signature="def process(self, data):",
            parent_class="MyClass",
        )
        assert defn.symbol_type == SymbolType.METHOD
        assert defn.parent_class == "MyClass"

    def test_to_dict_minimal(self):
        """Test serialization with only required fields."""
        defn = SymbolDefinition(
            name="foo",
            symbol_type=SymbolType.FUNCTION,
            line_start=1,
            line_end=5,
        )
        data = defn.to_dict()
        assert data == {
            "name": "foo",
            "symbol_type": "function",
            "line_start": 1,
            "line_end": 5,
        }

    def test_to_dict_full(self):
        """Test serialization with all fields."""
        defn = SymbolDefinition(
            name="MyClass",
            symbol_type=SymbolType.CLASS,
            line_start=1,
            line_end=100,
            signature="class MyClass",
            decorators=["dataclass"],
            bases=["Base"],
            docstring="A sample class",
            parent_class=None,  # Should not be included
        )
        data = defn.to_dict()
        assert data["signature"] == "class MyClass"
        assert data["decorators"] == ["dataclass"]
        assert data["bases"] == ["Base"]
        assert data["docstring"] == "A sample class"
        assert "parent_class" not in data  # None values excluded

    @pytest.mark.extended
    def test_from_dict_minimal(self):
        """Test deserialization with minimal data."""
        data = {
            "name": "foo",
            "symbol_type": "function",
            "line_start": 1,
            "line_end": 5,
        }
        defn = SymbolDefinition.from_dict(data)
        assert defn.name == "foo"
        assert defn.symbol_type == SymbolType.FUNCTION
        assert defn.signature is None
        assert defn.decorators is None

    def test_roundtrip_serialization(self):
        """Test serialization/deserialization roundtrip."""
        original = SymbolDefinition(
            name="process",
            symbol_type=SymbolType.METHOD,
            line_start=10,
            line_end=30,
            signature="def process(self):",
            decorators=["abstractmethod"],
            parent_class="BaseClass",
        )
        data = original.to_dict()
        restored = SymbolDefinition.from_dict(data)

        assert restored.name == original.name
        assert restored.symbol_type == original.symbol_type
        assert restored.line_start == original.line_start
        assert restored.line_end == original.line_end
        assert restored.signature == original.signature
        assert restored.decorators == original.decorators
        assert restored.parent_class == original.parent_class


class TestSymbolReference:
    """Tests for SymbolReference model."""

    @pytest.mark.extended
    def test_import_reference(self):
        """Test creating an import reference."""
        ref = SymbolReference(
            name="os",
            reference_type=ReferenceType.IMPORT,
            line_number=1,
            resolved_module="<stdlib:os>",
            resolved_symbol="os",
            module_name="os",
        )
        assert ref.name == "os"
        assert ref.reference_type == ReferenceType.IMPORT
        assert ref.resolved_module == "<stdlib:os>"

    @pytest.mark.extended
    def test_from_import_reference(self):
        """Test creating a 'from module import name' reference."""
        ref = SymbolReference(
            name="Path",
            reference_type=ReferenceType.IMPORT,
            line_number=2,
            resolved_module="<stdlib:pathlib>",
            resolved_symbol="Path",
            module_name="pathlib",
            is_relative=False,
            relative_level=0,
        )
        assert ref.module_name == "pathlib"
        assert ref.is_relative is False

    @pytest.mark.extended
    def test_relative_import_reference(self):
        """Test creating a relative import reference."""
        ref = SymbolReference(
            name="utils",
            reference_type=ReferenceType.IMPORT,
            line_number=3,
            resolved_module="/path/to/utils.py",
            resolved_symbol="utils",
            module_name=".",
            is_relative=True,
            relative_level=1,
        )
        assert ref.is_relative is True
        assert ref.relative_level == 1

    @pytest.mark.extended
    def test_function_call_reference(self):
        """Test creating a function call reference."""
        ref = SymbolReference(
            name="process_data",
            reference_type=ReferenceType.FUNCTION_CALL,
            line_number=50,
            resolved_module="/path/to/module.py",
            resolved_symbol="process_data",
            caller_context="main",
            is_method_call=False,
        )
        assert ref.reference_type == ReferenceType.FUNCTION_CALL
        assert ref.caller_context == "main"
        assert ref.is_method_call is False

    @pytest.mark.extended
    def test_class_reference(self):
        """Test creating a class inheritance reference."""
        ref = SymbolReference(
            name="BaseClass",
            reference_type=ReferenceType.CLASS_REFERENCE,
            line_number=10,
            resolved_module="/path/to/base.py",
            resolved_symbol="BaseClass",
            metadata={"child_class": "MyClass", "inheritance_order": "0"},
        )
        assert ref.reference_type == ReferenceType.CLASS_REFERENCE
        assert ref.metadata["child_class"] == "MyClass"

    @pytest.mark.extended
    def test_aliased_import(self):
        """Test import with alias."""
        ref = SymbolReference(
            name="np",  # Alias used in code
            reference_type=ReferenceType.IMPORT,
            line_number=1,
            resolved_module="<third-party:numpy>",
            resolved_symbol="numpy",  # Original name
            module_name="numpy",
            alias="np",
        )
        assert ref.name == "np"
        assert ref.alias == "np"
        assert ref.resolved_symbol == "numpy"

    @pytest.mark.extended
    def test_wildcard_import(self):
        """Test wildcard import reference."""
        ref = SymbolReference(
            name="*",
            reference_type=ReferenceType.IMPORT,
            line_number=1,
            resolved_module="<stdlib:os>",
            resolved_symbol="*",
            module_name="os",
            is_wildcard=True,
        )
        assert ref.is_wildcard is True

    def test_to_dict_minimal(self):
        """Test serialization with minimal fields."""
        ref = SymbolReference(
            name="foo",
            reference_type=ReferenceType.IMPORT,
            line_number=1,
        )
        data = ref.to_dict()
        assert data == {
            "name": "foo",
            "reference_type": "import",
            "line_number": 1,
        }

    def test_to_dict_full(self):
        """Test serialization with all fields."""
        ref = SymbolReference(
            name="helper",
            reference_type=ReferenceType.FUNCTION_CALL,
            line_number=10,
            resolved_module="/path/to/utils.py",
            resolved_symbol="helper",
            module_name="utils",
            is_relative=True,
            relative_level=1,
            alias="h",
            is_wildcard=False,
            is_conditional=True,
            is_method_call=True,
            caller_context="main",
            metadata={"key": "value"},
        )
        data = ref.to_dict()
        assert data["resolved_module"] == "/path/to/utils.py"
        assert data["is_relative"] is True
        assert data["relative_level"] == 1
        assert data["alias"] == "h"
        assert data["is_conditional"] is True
        assert data["is_method_call"] is True
        assert data["caller_context"] == "main"
        assert data["metadata"] == {"key": "value"}

    def test_roundtrip_serialization(self):
        """Test serialization/deserialization roundtrip."""
        original = SymbolReference(
            name="process",
            reference_type=ReferenceType.FUNCTION_CALL,
            line_number=25,
            resolved_module="/module.py",
            resolved_symbol="process",
            caller_context="handler",
            metadata={"call_pattern": "simple"},
        )
        data = original.to_dict()
        restored = SymbolReference.from_dict(data)

        assert restored.name == original.name
        assert restored.reference_type == original.reference_type
        assert restored.line_number == original.line_number
        assert restored.resolved_module == original.resolved_module
        assert restored.caller_context == original.caller_context
        assert restored.metadata == original.metadata


class TestFileSymbolData:
    """Tests for FileSymbolData model."""

    @pytest.mark.extended
    def test_basic_instantiation(self):
        """Test creating a FileSymbolData instance."""
        data = FileSymbolData(
            filepath="/path/to/module.py",
            definitions=[],
            references=[],
            parse_time=time.time(),
        )
        assert data.filepath == "/path/to/module.py"
        assert data.definitions == []
        assert data.references == []
        assert data.is_valid is True

    @pytest.mark.extended
    def test_with_definitions_and_references(self):
        """Test FileSymbolData with definitions and references."""
        func_def = SymbolDefinition(
            name="my_func",
            symbol_type=SymbolType.FUNCTION,
            line_start=5,
            line_end=15,
        )
        import_ref = SymbolReference(
            name="os",
            reference_type=ReferenceType.IMPORT,
            line_number=1,
        )

        data = FileSymbolData(
            filepath="/test.py",
            definitions=[func_def],
            references=[import_ref],
            parse_time=time.time(),
        )

        assert len(data.definitions) == 1
        assert len(data.references) == 1
        assert data.definitions[0].name == "my_func"
        assert data.references[0].name == "os"

    @pytest.mark.extended
    def test_get_definition_found(self):
        """Test looking up a definition by name."""
        class_def = SymbolDefinition(
            name="MyClass",
            symbol_type=SymbolType.CLASS,
            line_start=10,
            line_end=50,
        )
        data = FileSymbolData(
            filepath="/test.py",
            definitions=[class_def],
            references=[],
            parse_time=time.time(),
        )

        result = data.get_definition("MyClass")
        assert result is not None
        assert result.name == "MyClass"

    @pytest.mark.extended
    def test_get_definition_not_found(self):
        """Test looking up a non-existent definition."""
        data = FileSymbolData(
            filepath="/test.py",
            definitions=[],
            references=[],
            parse_time=time.time(),
        )

        result = data.get_definition("NonExistent")
        assert result is None

    @pytest.mark.extended
    def test_get_definitions_by_type(self):
        """Test filtering definitions by type."""
        func1 = SymbolDefinition(
            name="func1", symbol_type=SymbolType.FUNCTION, line_start=1, line_end=5
        )
        func2 = SymbolDefinition(
            name="func2", symbol_type=SymbolType.FUNCTION, line_start=10, line_end=15
        )
        class1 = SymbolDefinition(
            name="Class1", symbol_type=SymbolType.CLASS, line_start=20, line_end=50
        )

        data = FileSymbolData(
            filepath="/test.py",
            definitions=[func1, func2, class1],
            references=[],
            parse_time=time.time(),
        )

        functions = data.get_definitions_by_type(SymbolType.FUNCTION)
        assert len(functions) == 2

        classes = data.get_definitions_by_type(SymbolType.CLASS)
        assert len(classes) == 1

    @pytest.mark.extended
    def test_get_references_by_type(self):
        """Test filtering references by type."""
        import_ref = SymbolReference(name="os", reference_type=ReferenceType.IMPORT, line_number=1)
        call_ref = SymbolReference(
            name="process", reference_type=ReferenceType.FUNCTION_CALL, line_number=10
        )

        data = FileSymbolData(
            filepath="/test.py",
            definitions=[],
            references=[import_ref, call_ref],
            parse_time=time.time(),
        )

        imports = data.get_references_by_type(ReferenceType.IMPORT)
        assert len(imports) == 1

        calls = data.get_references_by_type(ReferenceType.FUNCTION_CALL)
        assert len(calls) == 1

    @pytest.mark.extended
    def test_get_import_references(self):
        """Test getting all import references."""
        import1 = SymbolReference(name="os", reference_type=ReferenceType.IMPORT, line_number=1)
        import2 = SymbolReference(name="sys", reference_type=ReferenceType.IMPORT, line_number=2)
        call = SymbolReference(
            name="func", reference_type=ReferenceType.FUNCTION_CALL, line_number=10
        )

        data = FileSymbolData(
            filepath="/test.py",
            definitions=[],
            references=[import1, import2, call],
            parse_time=time.time(),
        )

        imports = data.get_import_references()
        assert len(imports) == 2

    @pytest.mark.extended
    def test_invalid_file(self):
        """Test marking a file as invalid (syntax error)."""
        data = FileSymbolData(
            filepath="/broken.py",
            definitions=[],
            references=[],
            parse_time=time.time(),
            is_valid=False,
            error_message="SyntaxError at line 5",
        )

        assert data.is_valid is False
        assert data.error_message == "SyntaxError at line 5"

    @pytest.mark.extended
    def test_dynamic_patterns(self):
        """Test tracking dynamic patterns."""
        data = FileSymbolData(
            filepath="/dynamic.py",
            definitions=[],
            references=[],
            parse_time=time.time(),
            has_dynamic_patterns=True,
            dynamic_pattern_types=["exec", "eval"],
        )

        assert data.has_dynamic_patterns is True
        assert "exec" in data.dynamic_pattern_types
        assert "eval" in data.dynamic_pattern_types

    def test_to_dict_minimal(self):
        """Test serialization with minimal data."""
        data = FileSymbolData(
            filepath="/test.py",
            definitions=[],
            references=[],
            parse_time=1234567890.0,
        )
        result = data.to_dict()

        assert result["filepath"] == "/test.py"
        assert result["definitions"] == []
        assert result["references"] == []
        assert result["parse_time"] == 1234567890.0
        assert result["is_valid"] is True

    def test_to_dict_with_symbols(self):
        """Test serialization with definitions and references."""
        func = SymbolDefinition(
            name="func", symbol_type=SymbolType.FUNCTION, line_start=1, line_end=5
        )
        ref = SymbolReference(name="os", reference_type=ReferenceType.IMPORT, line_number=1)

        data = FileSymbolData(
            filepath="/test.py",
            definitions=[func],
            references=[ref],
            parse_time=1234567890.0,
        )
        result = data.to_dict()

        assert len(result["definitions"]) == 1
        assert len(result["references"]) == 1
        assert result["definitions"][0]["name"] == "func"
        assert result["references"][0]["name"] == "os"

    def test_roundtrip_serialization(self):
        """Test serialization/deserialization roundtrip."""
        func = SymbolDefinition(
            name="process",
            symbol_type=SymbolType.FUNCTION,
            line_start=10,
            line_end=30,
            signature="def process(data):",
        )
        ref = SymbolReference(
            name="helper",
            reference_type=ReferenceType.FUNCTION_CALL,
            line_number=20,
            resolved_module="/helper.py",
        )

        original = FileSymbolData(
            filepath="/test.py",
            definitions=[func],
            references=[ref],
            parse_time=1234567890.0,
            has_dynamic_patterns=True,
            dynamic_pattern_types=["exec"],
        )

        data = original.to_dict()
        restored = FileSymbolData.from_dict(data)

        assert restored.filepath == original.filepath
        assert len(restored.definitions) == 1
        assert len(restored.references) == 1
        assert restored.definitions[0].name == "process"
        assert restored.references[0].name == "helper"
        assert restored.has_dynamic_patterns is True
        assert "exec" in restored.dynamic_pattern_types
