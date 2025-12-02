# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Import relationship detector plugin.

This module implements the ImportDetector plugin that detects import
relationships in Python code and resolves them to file paths.

Supports:
- import module
- from module import name
- Relative imports: from . import, from .. import
- Module resolution to project-local file paths
- Standard library and third-party package detection

See TDD Section 3.5.2.1 for detailed specifications.
"""

import ast
import logging
from pathlib import Path
from typing import List, Optional

from ..models import Relationship, RelationshipType
from .base import RelationshipDetector

logger = logging.getLogger(__name__)


class ImportDetector(RelationshipDetector):
    """Detector for import relationships in Python code.

    Detects import statements and resolves them to file paths when possible.
    Implements the detector plugin pattern from DD-1.

    Patterns Detected:
    - import module
    - import package.submodule
    - from module import name
    - from package import submodule
    - Relative imports: from . import name, from .. import name

    Module Resolution (TDD Section 3.5.2.1):
    1. Same directory: module_name.py or module_name/__init__.py
    2. Parent packages (up to project root)
    3. Standard library (mark as <stdlib:module_name>)
    4. Third-party (mark as <third-party:package_name>)
    5. Unresolved (mark as <unresolved:module_name>)

    Priority: 100 (Foundation detector - runs first to build import map)

    See TDD Section 3.4.4 for detector interface specifications.
    """

    # Python standard library modules (Python 3.9+)
    # This is a curated list of common stdlib modules
    STDLIB_MODULES = frozenset(
        [
            # Built-in modules
            "sys",
            "os",
            "io",
            "time",
            "re",
            "math",
            "random",
            "datetime",
            "calendar",
            # Collections and data structures
            "collections",
            "array",
            "heapq",
            "bisect",
            "weakref",
            "types",
            "copy",
            "pprint",
            "reprlib",
            "enum",
            # Functional programming
            "itertools",
            "functools",
            "operator",
            # File and path handling
            "pathlib",
            "glob",
            "shutil",
            "tempfile",
            # Data persistence
            "pickle",
            "shelve",
            "json",
            "csv",
            "sqlite3",
            # Compression
            "zlib",
            "gzip",
            "bz2",
            "lzma",
            "zipfile",
            "tarfile",
            # Cryptography
            "hashlib",
            "hmac",
            "secrets",
            # OS interface
            "subprocess",
            "threading",
            "multiprocessing",
            "concurrent",
            "signal",
            "socket",
            # Internet protocols
            "email",
            "json",
            "urllib",
            "http",
            "ftplib",
            "smtplib",
            # Structured markup
            "html",
            "xml",
            # Text processing
            "string",
            "textwrap",
            "unicodedata",
            "stringprep",
            "difflib",
            # Binary data
            "struct",
            "codecs",
            # Testing
            "unittest",
            "doctest",
            # Logging
            "logging",
            "warnings",
            # Runtime
            "importlib",
            "pkgutil",
            "modulefinder",
            "runpy",
            # Language
            "ast",
            "symtable",
            "token",
            "keyword",
            "tokenize",
            "tabnanny",
            "pydoc",
            # Typing
            "typing",
            "typing_extensions",
            # Context managers
            "contextlib",
            # ABC
            "abc",
            # Data classes
            "dataclasses",
            # Argument parsing
            "argparse",
            "optparse",
            "getopt",
            # Config
            "configparser",
            # Platform
            "platform",
            # Others
            "inspect",
            "traceback",
            "gc",
            "atexit",
        ]
    )

    def detect(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
    ) -> List[Relationship]:
        """Detect import relationships in an AST node.

        Args:
            node: AST node to analyze.
            filepath: Absolute path to the file being analyzed.
            module_ast: The root AST node of the entire module (for context).

        Returns:
            List of detected import relationships. Empty list if no imports found.
        """
        relationships: List[Relationship] = []

        # Handle 'import module' statements
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name
                target_file = self._resolve_module(module_name, filepath, is_relative=False)

                # Determine import style
                if alias.asname:
                    # import foo as bar (aliased import - will be handled by AliasedImportDetector)
                    # For now, track basic import relationship
                    import_style = "import_as"
                    imported_names = f"{alias.name} as {alias.asname}"
                else:
                    import_style = "import"
                    imported_names = alias.name

                rel = Relationship(
                    source_file=filepath,
                    target_file=target_file,
                    relationship_type=RelationshipType.IMPORT,
                    line_number=node.lineno,
                    source_symbol=None,  # import statements don't have source symbols
                    target_symbol=imported_names,
                    metadata={
                        "import_style": import_style,
                        "module_name": module_name,
                    },
                )
                relationships.append(rel)

        # Handle 'from module import name' statements
        elif isinstance(node, ast.ImportFrom):
            # Extract module name (None for relative imports like 'from . import foo')
            module_name = node.module if node.module else ""
            level = node.level if node.level else 0  # 0 = absolute, 1 = '.', 2 = '..', etc.

            # Track each imported name
            for alias in node.names:
                # For relative imports with no module (e.g., 'from . import utils'),
                # the target module is in alias.name, not node.module
                if level > 0 and not module_name:
                    # e.g., 'from . import utils' -> target is 'utils' in current directory
                    actual_module_name = alias.name if alias.name != "*" else ""
                else:
                    actual_module_name = module_name

                # Resolve module path
                if level > 0:
                    # Relative import
                    target_file = self._resolve_relative_import(actual_module_name, filepath, level)
                else:
                    # Absolute import
                    target_file = self._resolve_module(
                        actual_module_name, filepath, is_relative=False
                    )

                if alias.asname:
                    # from foo import bar as baz (aliased import)
                    import_style = "from_import_as"
                    imported_names = f"{alias.name} as {alias.asname}"
                else:
                    import_style = "from_import"
                    imported_names = alias.name

                rel = Relationship(
                    source_file=filepath,
                    target_file=target_file,
                    relationship_type=RelationshipType.IMPORT,
                    line_number=node.lineno,
                    source_symbol=None,
                    target_symbol=imported_names,
                    metadata={
                        "import_style": import_style,
                        "module_name": module_name if module_name else f"{'.' * level}",
                        "relative_level": str(level),
                    },
                )
                relationships.append(rel)

        return relationships

    def _resolve_module(self, module_name: str, filepath: str, is_relative: bool) -> str:
        """Resolve a module name to a file path.

        Implements the resolution order from TDD Section 3.5.2.1:
        1. Same directory: module_name.py or module_name/__init__.py
        2. Parent packages (up to project root)
        3. Standard library (mark as <stdlib:module_name>)
        4. Third-party (mark as <third-party:package_name>)
        5. Unresolved (mark as <unresolved:module_name>)

        Args:
            module_name: Name of the module to resolve (e.g., 'os', 'foo.bar').
            filepath: Absolute path to the file containing the import.
            is_relative: Whether this is a relative import.

        Returns:
            Resolved file path, or special marker for stdlib/third-party/unresolved.
        """
        # Handle empty module name (from . import foo)
        if not module_name:
            return "<unresolved:>"

        # Check if it's a standard library module
        base_module = module_name.split(".")[0]
        if base_module in self.STDLIB_MODULES:
            return f"<stdlib:{module_name}>"

        # Try to resolve to project-local file
        current_dir = Path(filepath).parent

        # Split module name into parts (e.g., 'foo.bar' -> ['foo', 'bar'])
        parts = module_name.split(".")

        # 1. Check same directory
        resolved = self._try_resolve_in_directory(current_dir, parts)
        if resolved:
            return str(resolved)

        # 2. Check parent packages up to project root
        # Walk up the directory tree until we find a directory without __init__.py
        # (that's the project root boundary)
        parent_dir = current_dir.parent
        while parent_dir != parent_dir.parent:  # Stop at filesystem root
            # Check if we're still inside a package (has __init__.py)
            if not (parent_dir / "__init__.py").exists():
                # We've reached the project root boundary
                # Try resolving from here
                resolved = self._try_resolve_in_directory(parent_dir, parts)
                if resolved:
                    return str(resolved)
                break

            # Try resolving from this parent directory
            resolved = self._try_resolve_in_directory(parent_dir, parts)
            if resolved:
                return str(resolved)

            parent_dir = parent_dir.parent

        # 3. Check if it's a known third-party package
        # For v0.1.0, we conservatively mark as third-party only if we have
        # strong evidence (module exists in site-packages).
        # Otherwise, mark as unresolved to be safe.
        if self._is_known_third_party(base_module):
            return f"<third-party:{module_name}>"

        # 4. Unresolved (default for non-stdlib, non-local, non-verified-third-party)
        return f"<unresolved:{module_name}>"

    def _resolve_relative_import(self, module_name: str, filepath: str, level: int) -> str:
        """Resolve a relative import to a file path.

        Args:
            module_name: Module name (empty string for 'from . import foo').
            filepath: Absolute path to the file containing the import.
            level: Number of parent directories to traverse (1 = '.', 2 = '..', etc.).

        Returns:
            Resolved file path, or special marker for unresolved.
        """
        current_dir = Path(filepath).parent

        # For level 1 (from . import), target is current directory
        # For level 2 (from .. import), target is parent directory
        # So we navigate up (level - 1) directories from current_dir
        target_dir = current_dir
        for _ in range(level - 1):
            parent = target_dir.parent
            if parent == target_dir:  # Reached filesystem root
                logger.warning(
                    f"⚠️ Relative import level {level} exceeds package depth in {filepath}"
                )
                return f"<unresolved:{'.' * level}{module_name}>"
            target_dir = parent

        # If module_name is empty, we're importing from the target directory itself
        if not module_name:
            # Check if target directory is a package (has __init__.py)
            init_file = target_dir / "__init__.py"
            if init_file.exists():
                return str(init_file)
            else:
                return f"<unresolved:{'.' * level}>"

        # Resolve module_name within target directory
        parts = module_name.split(".")
        resolved = self._try_resolve_in_directory(target_dir, parts)
        if resolved:
            return str(resolved)

        return f"<unresolved:{'.' * level}{module_name}>"

    def _try_resolve_in_directory(self, directory: Path, module_parts: List[str]) -> Optional[Path]:
        """Try to resolve a module within a specific directory.

        Handles both module files and packages:
        - foo.bar -> directory/foo/bar.py or directory/foo/bar/__init__.py

        Ambiguity Handling (TDD Section 3.5.2.1):
        - If both utils.py and utils/__init__.py exist, prefer utils.py

        Args:
            directory: Directory to search in.
            module_parts: Module name split into parts (e.g., ['foo', 'bar']).

        Returns:
            Resolved Path if found, None otherwise.
        """
        if not module_parts:
            return None

        # Build path iteratively
        current_path = directory
        for i, part in enumerate(module_parts):
            # Last part: check for both .py file and package
            if i == len(module_parts) - 1:
                # Check for module file first (higher priority per TDD 3.5.2.1)
                module_file = current_path / f"{part}.py"
                package_init = current_path / part / "__init__.py"

                if module_file.exists():
                    return module_file
                elif package_init.exists():
                    return package_init
                else:
                    return None
            else:
                # Intermediate part: must be a package
                current_path = current_path / part
                if not (current_path / "__init__.py").exists():
                    return None

        return None

    def _is_known_third_party(self, module_name: str) -> bool:
        """Check if a module is a known third-party package.

        This is a conservative check - we only mark as third-party if we can
        verify the module exists in sys.path. Otherwise, we mark as unresolved.

        For v0.1.0, we use a simple heuristic: try to import the module spec.
        If it exists and is not in stdlib, it's third-party.

        Args:
            module_name: Base module name to check.

        Returns:
            True if verified third-party, False if unresolved/unknown.
        """
        # Not stdlib is a prerequisite for third-party
        if module_name in self.STDLIB_MODULES:
            return False

        # For v0.1.0, we use a simple heuristic: check if importlib can find it
        try:
            import importlib.util

            spec = importlib.util.find_spec(module_name)
            if spec is not None and spec.origin is not None:
                # Module exists and has a file location
                # This likely means it's installed as a third-party package
                return True
        except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
            # Module doesn't exist or can't be found
            pass

        return False

    def priority(self) -> int:
        """Return detector priority.

        ImportDetector has high priority (100) as it's a foundation detector
        that builds import maps for other detectors to use.

        Returns:
            Priority value (100).
        """
        return 100

    def name(self) -> str:
        """Return detector name.

        Returns:
            Detector name: "ImportDetector".
        """
        return "ImportDetector"
