# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Integration tests for two-phase analysis pipeline (Issue #125).

Tests the full two-phase analysis flow:
Phase 1: AST -> FileSymbolData (via detectors)
Phase 2: FileSymbolData -> Relationships (via RelationshipBuilder)

These tests verify:
- analyze_file_two_phase() produces correct relationships
- analyze_project_two_phase() provides cross-file resolution
- Service integration with two-phase mode
- Configuration switch between direct and two-phase modes
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
    def two_phase_config(self, tmp_path: Path) -> Config:
        """Create config with two-phase analysis enabled."""
        config_file = tmp_path / ".cross_file_context_links.yml"
        config_file.write_text("use_two_phase_analysis: true\n")
        return Config(config_path=config_file)

    @pytest.fixture
    def direct_config(self, tmp_path: Path) -> Config:
        """Create config with direct analysis (explicitly disabled)."""
        config_file = tmp_path / ".cross_file_context_links.yml"
        config_file.write_text("use_two_phase_analysis: false\n")
        return Config(config_path=config_file)

    def test_service_two_phase_analyze_file(
        self, temp_project: Dict[str, Path], two_phase_config: Config
    ) -> None:
        """Test service analyze_file in two-phase mode."""
        service = CrossFileContextService(
            config=two_phase_config, project_root=str(temp_project["root"])
        )

        try:
            result = service.analyze_file(str(temp_project["main"]))
            assert result is True

            # Check relationships were created
            deps = service.get_dependencies(str(temp_project["main"]))
            assert len(deps) > 0
        finally:
            service.shutdown()

    def test_service_two_phase_analyze_directory(
        self, temp_project: Dict[str, Path], two_phase_config: Config
    ) -> None:
        """Test service analyze_directory in two-phase mode."""
        service = CrossFileContextService(
            config=two_phase_config, project_root=str(temp_project["root"])
        )

        try:
            stats = service.analyze_directory(str(temp_project["src"]))

            assert stats["success"] >= 2
            assert stats["failed"] == 0

            # Verify relationships
            all_rels = service._graph.get_all_relationships()
            assert len(all_rels) > 0
        finally:
            service.shutdown()

    def test_service_direct_vs_two_phase_produces_relationships(
        self, temp_project: Dict[str, Path], direct_config: Config, two_phase_config: Config
    ) -> None:
        """Test both modes produce relationships."""
        # Direct mode
        direct_service = CrossFileContextService(
            config=direct_config, project_root=str(temp_project["root"])
        )
        try:
            direct_service.analyze_directory(str(temp_project["src"]))
            direct_rels = direct_service._graph.get_all_relationships()
        finally:
            direct_service.shutdown()

        # Two-phase mode
        two_phase_service = CrossFileContextService(
            config=two_phase_config, project_root=str(temp_project["root"])
        )
        try:
            two_phase_service.analyze_directory(str(temp_project["src"]))
            two_phase_rels = two_phase_service._graph.get_all_relationships()
        finally:
            two_phase_service.shutdown()

        # Both should produce relationships
        assert len(direct_rels) > 0
        assert len(two_phase_rels) > 0

    def test_service_two_phase_relationship_builder_initialized(
        self, temp_project: Dict[str, Path], two_phase_config: Config
    ) -> None:
        """Test that RelationshipBuilder is initialized in two-phase mode."""
        service = CrossFileContextService(
            config=two_phase_config, project_root=str(temp_project["root"])
        )

        try:
            assert service._relationship_builder is not None
        finally:
            service.shutdown()

    def test_service_direct_mode_no_relationship_builder(
        self, temp_project: Dict[str, Path], direct_config: Config
    ) -> None:
        """Test that RelationshipBuilder is not initialized in direct mode."""
        service = CrossFileContextService(
            config=direct_config, project_root=str(temp_project["root"])
        )

        try:
            assert service._relationship_builder is None
        finally:
            service.shutdown()


class TestConfigTwoPhaseOption:
    """Tests for two-phase analysis configuration."""

    def test_config_default_is_two_phase_mode(self, tmp_path: Path) -> None:
        """Test default configuration uses two-phase mode."""
        config = Config(config_path=tmp_path / "nonexistent.yml")
        assert config.use_two_phase_analysis is True

    def test_config_enable_two_phase(self, tmp_path: Path) -> None:
        """Test enabling two-phase mode via config."""
        config_file = tmp_path / ".cross_file_context_links.yml"
        config_file.write_text("use_two_phase_analysis: true\n")

        config = Config(config_path=config_file)
        assert config.use_two_phase_analysis is True

    def test_config_disable_two_phase(self, tmp_path: Path) -> None:
        """Test explicitly disabling two-phase mode."""
        config_file = tmp_path / ".cross_file_context_links.yml"
        config_file.write_text("use_two_phase_analysis: false\n")

        config = Config(config_path=config_file)
        assert config.use_two_phase_analysis is False

    def test_config_invalid_value_uses_default(self, tmp_path: Path) -> None:
        """Test invalid config value falls back to default."""
        config_file = tmp_path / ".cross_file_context_links.yml"
        config_file.write_text("use_two_phase_analysis: 'yes'\n")  # Invalid: not a bool

        config = Config(config_path=config_file)
        assert config.use_two_phase_analysis is True  # Default
