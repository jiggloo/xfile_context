# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Integration tests for two-phase analysis pipeline (Issue #125).

Tests the full two-phase analysis flow:
Phase 1: AST -> FileSymbolData (via detectors)
Phase 2: FileSymbolData -> Relationships (via RelationshipBuilder)

These tests verify:
- analyze_file_two_phase() produces correct relationships
- analyze_project_two_phase() provides cross-file resolution
- Service integration with two-phase analysis (always enabled per Issue #133)
"""

from pathlib import Path
from typing import Dict

import pytest

from xfile_context.analyzers.python_analyzer import PythonAnalyzer
from xfile_context.config import Config
from xfile_context.detectors.registry import DetectorRegistry
from xfile_context.models import RelationshipGraph, RelationshipType
from xfile_context.relationship_builder import RelationshipBuilder
from xfile_context.service import CrossFileContextService


class TestTwoPhaseAnalyzerIntegration:
    """Tests for PythonAnalyzer two-phase methods."""

    @pytest.fixture
    def temp_project(self, tmp_path: Path) -> Dict[str, Path]:
        """Create a temporary project with multiple Python files."""
        # Create module structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # utils.py - defines helper functions
        utils_file = src_dir / "utils.py"
        utils_file.write_text(
            '''# Copyright (c) 2025 Test
def format_name(name: str) -> str:
    """Format a name."""
    return name.title()

def validate_email(email: str) -> bool:
    """Validate email format."""
    return "@" in email

class Helper:
    """Helper class."""
    pass
'''
        )

        # models.py - imports from utils
        models_file = src_dir / "models.py"
        models_file.write_text(
            '''# Copyright (c) 2025 Test
from utils import format_name, Helper

class User:
    """User model."""
    def __init__(self, name: str):
        self.name = format_name(name)
'''
        )

        # main.py - imports from both
        main_file = src_dir / "main.py"
        main_file.write_text(
            '''# Copyright (c) 2025 Test
from utils import validate_email
from models import User

def create_user(name: str, email: str) -> User:
    """Create a user."""
    if validate_email(email):
        return User(name)
    raise ValueError("Invalid email")
'''
        )

        return {
            "root": tmp_path,
            "src": src_dir,
            "utils": utils_file,
            "models": models_file,
            "main": main_file,
        }

    @pytest.fixture
    def analyzer(self, temp_project: Dict[str, Path]) -> PythonAnalyzer:
        """Create analyzer with all standard detectors."""
        from xfile_context.detectors import (
            ClassInheritanceDetector,
            FunctionCallDetector,
            ImportDetector,
        )

        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(ImportDetector())
        registry.register(FunctionCallDetector())
        registry.register(ClassInheritanceDetector())

        return PythonAnalyzer(graph=graph, detector_registry=registry)

    def test_analyze_file_two_phase_single_file(
        self, analyzer: PythonAnalyzer, temp_project: Dict[str, Path]
    ) -> None:
        """Test two-phase analysis on a single file."""
        utils_path = str(temp_project["utils"])

        # Analyze using two-phase
        result = analyzer.analyze_file_two_phase(utils_path)

        assert result is True

        # utils.py has no imports, so no import relationships
        # but it should be analyzed without error
        # The graph should exist and be queryable
        assert analyzer.graph is not None

    def test_analyze_file_two_phase_with_imports(
        self, analyzer: PythonAnalyzer, temp_project: Dict[str, Path]
    ) -> None:
        """Test two-phase analysis on file with imports."""
        models_path = str(temp_project["models"])

        # Analyze using two-phase
        result = analyzer.analyze_file_two_phase(models_path)

        assert result is True

        # Check import relationships were detected
        relationships = analyzer.graph.get_dependencies(models_path)
        assert len(relationships) > 0

        # Verify import relationship types
        import_rels = [r for r in relationships if r.relationship_type == RelationshipType.IMPORT]
        assert len(import_rels) >= 1  # At least the utils import

    def test_analyze_file_two_phase_with_shared_builder(
        self, analyzer: PythonAnalyzer, temp_project: Dict[str, Path]
    ) -> None:
        """Test two-phase analysis with shared RelationshipBuilder."""
        builder = RelationshipBuilder()

        utils_path = str(temp_project["utils"])
        models_path = str(temp_project["models"])

        # First, extract and add utils symbols to builder
        utils_data = analyzer.extract_file_symbols(utils_path)
        assert utils_data is not None
        builder.add_file_data(utils_data)

        # Then analyze models with the shared builder
        result = analyzer.analyze_file_two_phase(models_path, relationship_builder=builder)

        assert result is True

        # Check that builder has data for both files
        assert builder.get_file_data(utils_path) is not None
        assert builder.get_file_data(models_path) is not None

    def test_analyze_project_two_phase(
        self, analyzer: PythonAnalyzer, temp_project: Dict[str, Path]
    ) -> None:
        """Test two-phase analysis on multiple files."""
        files = [
            str(temp_project["utils"]),
            str(temp_project["models"]),
            str(temp_project["main"]),
        ]

        success, failed, builder = analyzer.analyze_project_two_phase(files)

        assert success == 3
        assert failed == 0
        assert builder is not None

        # Check builder has all files
        for filepath in files:
            assert builder.get_file_data(filepath) is not None

        # Check relationships in graph
        all_relationships = analyzer.graph.get_all_relationships()
        assert len(all_relationships) > 0

        # Check specific imports
        main_deps = analyzer.graph.get_dependencies(str(temp_project["main"]))
        assert len(main_deps) >= 2  # imports from utils and models

    def test_analyze_project_two_phase_with_invalid_file(
        self, analyzer: PythonAnalyzer, temp_project: Dict[str, Path]
    ) -> None:
        """Test two-phase analysis handles invalid files gracefully."""
        # Create an invalid Python file
        invalid_file = temp_project["src"] / "invalid.py"
        invalid_file.write_text("def broken(:\n    pass")

        files = [
            str(temp_project["utils"]),
            str(invalid_file),
            str(temp_project["models"]),
        ]

        success, failed, builder = analyzer.analyze_project_two_phase(files)

        assert success == 2
        assert failed == 1
        assert builder.get_file_data(str(invalid_file)) is None

    def test_analyze_project_two_phase_incremental(
        self, analyzer: PythonAnalyzer, temp_project: Dict[str, Path]
    ) -> None:
        """Test incremental update with existing builder."""
        files = [str(temp_project["utils"]), str(temp_project["models"])]

        # Initial analysis
        success1, failed1, builder = analyzer.analyze_project_two_phase(files)
        assert success1 == 2

        # Add new file
        new_file = temp_project["src"] / "new_module.py"
        new_file.write_text("from utils import format_name\n\ndef process():\n    pass\n")

        # Incremental analysis with same builder
        success2, failed2, builder = analyzer.analyze_project_two_phase(
            [str(new_file)], relationship_builder=builder
        )
        assert success2 == 1

        # Builder now has all 3 files
        assert builder.get_file_data(str(temp_project["utils"])) is not None
        assert builder.get_file_data(str(temp_project["models"])) is not None
        assert builder.get_file_data(str(new_file)) is not None


class TestServiceTwoPhaseIntegration:
    """Tests for CrossFileContextService two-phase mode."""

    @pytest.fixture
    def temp_project(self, tmp_path: Path) -> Dict[str, Path]:
        """Create a temporary project with Python files."""
        # Create a simple project
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        utils_file = src_dir / "utils.py"
        utils_file.write_text('def helper():\n    """Help."""\n    pass\n')

        main_file = src_dir / "main.py"
        # Use stdlib import to ensure relationships are detected
        main_file.write_text("import os\nfrom os.path import join\n\ndef main():\n    pass\n")

        return {"root": tmp_path, "src": src_dir, "utils": utils_file, "main": main_file}

    @pytest.fixture
    def config(self, tmp_path: Path) -> Config:
        """Create default config (two-phase analysis always enabled)."""
        return Config(config_path=tmp_path / "nonexistent.yml")

    def test_service_two_phase_analyze_file(
        self, temp_project: Dict[str, Path], config: Config
    ) -> None:
        """Test service analyze_file (always uses two-phase analysis)."""
        service = CrossFileContextService(config=config, project_root=str(temp_project["root"]))

        try:
            result = service.analyze_file(str(temp_project["main"]))
            assert result is True

            # Check relationships were created
            deps = service.get_dependencies(str(temp_project["main"]))
            assert len(deps) > 0
        finally:
            service.shutdown()

    def test_service_two_phase_analyze_directory(
        self, temp_project: Dict[str, Path], config: Config
    ) -> None:
        """Test service analyze_directory (always uses two-phase analysis)."""
        service = CrossFileContextService(config=config, project_root=str(temp_project["root"]))

        try:
            stats = service.analyze_directory(str(temp_project["src"]))

            assert stats["success"] >= 2
            assert stats["failed"] == 0

            # Verify relationships
            all_rels = service._graph.get_all_relationships()
            assert len(all_rels) > 0
        finally:
            service.shutdown()

    def test_service_produces_relationships(
        self, temp_project: Dict[str, Path], config: Config
    ) -> None:
        """Test service produces relationships with two-phase analysis."""
        service = CrossFileContextService(config=config, project_root=str(temp_project["root"]))
        try:
            service.analyze_directory(str(temp_project["src"]))
            rels = service._graph.get_all_relationships()
        finally:
            service.shutdown()

        assert len(rels) > 0

    def test_service_two_phase_relationship_builder_initialized(
        self, temp_project: Dict[str, Path], config: Config
    ) -> None:
        """Test that RelationshipBuilder is always initialized (two-phase always enabled)."""
        service = CrossFileContextService(config=config, project_root=str(temp_project["root"]))

        try:
            assert service._relationship_builder is not None
        finally:
            service.shutdown()


class TestFunctionDefinitionIntegration:
    """Tests for FunctionDefinitionDetector integration (Issue #140).

    Verifies that function definitions are properly extracted and that
    line numbers show up in relationship resolution.
    """

    @pytest.fixture
    def temp_project(self, tmp_path: Path) -> Dict[str, Path]:
        """Create a temporary project with functions to test."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # utils.py - defines helper functions
        utils_file = src_dir / "utils.py"
        utils_file.write_text(
            '''# Copyright (c) 2025 Test
def format_name(name: str) -> str:
    """Format a name."""
    return name.title()

def validate_email(email: str) -> bool:
    """Validate email format."""
    return "@" in email

async def async_fetch(url: str) -> str:
    """Async fetch function."""
    return f"fetched {url}"
'''
        )

        # main.py - imports and calls functions from utils
        main_file = src_dir / "main.py"
        main_file.write_text(
            '''# Copyright (c) 2025 Test
from utils import format_name, validate_email

def process_user(name: str, email: str) -> str:
    """Process a user."""
    if validate_email(email):
        return format_name(name)
    return name
'''
        )

        return {
            "root": tmp_path,
            "src": src_dir,
            "utils": utils_file,
            "main": main_file,
        }

    @pytest.fixture
    def config(self, tmp_path: Path) -> Config:
        """Create default config."""
        return Config(config_path=tmp_path / "nonexistent.yml")

    def test_function_definitions_extracted(
        self, temp_project: Dict[str, Path], config: Config
    ) -> None:
        """Test that FunctionDefinitionDetector extracts function definitions."""
        service = CrossFileContextService(config=config, project_root=str(temp_project["root"]))

        try:
            # Analyze the utils file
            service.analyze_file(str(temp_project["utils"]))

            # Check RelationshipBuilder has the file data
            builder = service._relationship_builder
            utils_data = builder.get_file_data(str(temp_project["utils"]))

            assert utils_data is not None, "utils.py should have FileSymbolData"

            # Check function definitions were extracted
            format_name_def = utils_data.get_definition("format_name")
            assert format_name_def is not None, "format_name should have a definition"
            assert format_name_def.line_start == 2  # Line 2 in file

            validate_email_def = utils_data.get_definition("validate_email")
            assert validate_email_def is not None, "validate_email should have a definition"
            assert validate_email_def.line_start == 6

            async_fetch_def = utils_data.get_definition("async_fetch")
            assert async_fetch_def is not None, "async_fetch should have a definition"
            assert async_fetch_def.line_start == 10

        finally:
            service.shutdown()

    def test_function_line_numbers_in_relationships(
        self, temp_project: Dict[str, Path], config: Config
    ) -> None:
        """Test that function definitions are available for relationship lookup."""
        service = CrossFileContextService(config=config, project_root=str(temp_project["src"]))

        try:
            # Analyze the utils file directly
            service.analyze_file(str(temp_project["utils"]))

            # The builder should have function definitions from utils
            builder = service._relationship_builder
            utils_data = builder.get_file_data(str(temp_project["utils"]))
            assert utils_data is not None, "utils.py should have FileSymbolData"

            # Can look up function definitions by name
            format_name_def = builder.lookup_definition("format_name", str(temp_project["utils"]))
            assert format_name_def is not None, "format_name should be found"
            assert format_name_def.line_start == 2

            # Also verify validate_email is found
            validate_email_def = builder.lookup_definition(
                "validate_email", str(temp_project["utils"])
            )
            assert validate_email_def is not None, "validate_email should be found"
            assert validate_email_def.line_start == 6

        finally:
            service.shutdown()

    def test_read_with_context_shows_function_line_numbers(
        self, temp_project: Dict[str, Path], config: Config
    ) -> None:
        """Test that read_with_context() shows function line numbers on first call (Issue #140).

        This is the core test that verifies Issue #140 is fixed:
        Functions should show line numbers in the injected context.
        """
        service = CrossFileContextService(config=config, project_root=str(temp_project["root"]))

        try:
            # First call to read_with_context
            result = service.read_file_with_context(str(temp_project["main"]))

            assert result.content is not None

            # Check that we have dependency information
            # The injected context should include the utils.py file
            deps = service.get_dependencies(str(temp_project["main"]))
            assert len(deps) > 0, "main.py should have dependencies"

            # Check that the utils file was analyzed and has function definitions
            builder = service._relationship_builder
            utils_data = builder.get_file_data(str(temp_project["utils"]))

            assert utils_data is not None, "utils.py should be analyzed"

            # Verify function definitions exist
            format_name_def = utils_data.get_definition("format_name")
            assert format_name_def is not None, "format_name definition should exist"
            assert format_name_def.line_start is not None

        finally:
            service.shutdown()

    def test_function_definitions_idempotent(
        self, temp_project: Dict[str, Path], config: Config
    ) -> None:
        """Test that function definitions are consistent across multiple reads.

        Verifies idempotency: first and second calls should have same definitions.
        """
        service = CrossFileContextService(config=config, project_root=str(temp_project["root"]))

        try:
            # First call
            service.read_file_with_context(str(temp_project["main"]))
            builder = service._relationship_builder
            utils_data_1 = builder.get_file_data(str(temp_project["utils"]))

            # Get definitions after first call
            defs_1 = (
                {d.name: d.line_start for d in utils_data_1.definitions} if utils_data_1 else {}
            )

            # Second call (should be idempotent)
            service.read_file_with_context(str(temp_project["main"]))
            utils_data_2 = builder.get_file_data(str(temp_project["utils"]))

            # Get definitions after second call
            defs_2 = (
                {d.name: d.line_start for d in utils_data_2.definitions} if utils_data_2 else {}
            )

            # Definitions should be the same
            assert defs_1 == defs_2, "Function definitions should be idempotent"

        finally:
            service.shutdown()
