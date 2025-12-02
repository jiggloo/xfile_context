# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Function call relationship detector plugin.

This module implements the FunctionCallDetector plugin that detects simple
function call relationships in Python code and resolves them to defining files.

v0.1.0 Scope (TDD Section 3.5.2.2):
- Simple function calls: function_name(args)
- Module-qualified calls: module.function(args) (if module imported)

v0.1.0 Limitations (Deferred to v0.1.1/v0.1.2):
- NO method chains: obj.method().other_method()
- NO nested attributes: obj.attr.method()
- These patterns are explicitly deferred per DD-1

Function Resolution Order (TDD Section 3.5.2.2):
1. Local scope: Check if function defined in current file
2. Imported names: Resolve via import tracking from ImportDetector
3. Built-in functions: Mark as <builtin:name>
4. Unresolved: Mark as <unresolved:name>

See TDD Section 3.5.2.2 for detailed specifications.
"""

import ast
import builtins
import logging
from typing import Dict, List, Optional, Set

from ..models import Relationship, RelationshipType
from .base import RelationshipDetector

logger = logging.getLogger(__name__)


class FunctionCallDetector(RelationshipDetector):
    """Detector for simple function call relationships in Python code.

    Detects direct function calls and resolves them to defining files when possible.
    Implements the detector plugin pattern from DD-1.

    Patterns Detected (v0.1.0):
    - Simple calls: function_name(args)
    - Module-qualified calls: module.function(args) (if module imported)

    Patterns NOT Detected (v0.1.0):
    - Method chains: obj.method().other() (deferred to v0.1.1)
    - Nested attributes: module.submodule.function() (deferred to v0.1.2)
    - Dynamic calls: getattr(obj, name)() (cannot be statically analyzed, EC-6)

    Function Resolution (TDD Section 3.5.2.2):
    1. Local scope: Check if function defined in current file
    2. Imported names: Use import relationships to resolve
    3. Built-in functions: Mark as <builtin:name>
    4. Unresolved: Mark as <unresolved:name>

    Priority: 50 (Core detector - runs after foundation detectors like ImportDetector)

    See TDD Section 3.4.4 for detector interface specifications.
    """

    # Python built-in functions (Python 3.8+)
    BUILTIN_FUNCTIONS = frozenset(dir(builtins))

    def __init__(self) -> None:
        """Initialize the detector.

        Note: Detector instances are reused across multiple files (per DetectorRegistry design).
        Caches are built once per file and invalidated when analyzing a different file.
        """
        # Cache for local function definitions (per-file cache)
        self._local_functions: Set[str] = set()
        # Cache for import mappings (per-file cache)
        self._import_map: Dict[str, str] = {}
        # Track which file the cache belongs to (for cache invalidation)
        self._cached_filepath: Optional[str] = None

    def detect(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
    ) -> List[Relationship]:
        """Detect function call relationships in an AST node.

        Args:
            node: AST node to analyze.
            filepath: Absolute path to the file being analyzed.
            module_ast: The root AST node of the entire module (for context).

        Returns:
            List of detected function call relationships. Empty list if no calls found.
        """
        relationships: List[Relationship] = []

        # Handle direct function calls (ast.Call nodes)
        if isinstance(node, ast.Call):
            # Build caches if analyzing a new file (invalidate cache on file change)
            # This prevents cache pollution when the same detector instance
            # is reused across multiple files (DetectorRegistry pattern)
            if self._cached_filepath != filepath:
                self._cached_filepath = filepath
                self._local_functions.clear()
                self._import_map.clear()
                self._build_local_function_cache(module_ast)

            # Only handle simple patterns in v0.1.0
            func_node = node.func

            # Pattern 1: Simple direct call - function_name(args)
            if isinstance(func_node, ast.Name):
                function_name = func_node.id
                target_file = self._resolve_function(function_name, filepath, module_ast)

                rel = Relationship(
                    source_file=filepath,
                    target_file=target_file,
                    relationship_type=RelationshipType.FUNCTION_CALL,
                    line_number=node.lineno,
                    source_symbol=self._get_call_context(node, module_ast),
                    target_symbol=function_name,
                    metadata={
                        "call_pattern": "simple",
                        "function_name": function_name,
                    },
                )
                relationships.append(rel)

            # Pattern 2: Module-qualified call - module.function(args)
            # Only if it's a simple attribute (not chained) AND the value is actually a module
            elif isinstance(func_node, ast.Attribute):
                # Check if this is a simple module.function pattern
                # (not a method chain like obj.method().other())
                if isinstance(func_node.value, ast.Name):
                    module_name = func_node.value.id
                    function_name = func_node.attr

                    # Build import map if not already built
                    if not self._import_map:
                        self._build_import_map(module_ast, filepath)

                    # Only treat as module-qualified call if module_name is actually imported
                    # This filters out instance method calls like obj.method()
                    if module_name in self._import_map:
                        # Resolve the module-qualified call
                        target_file = self._resolve_module_qualified_call(
                            module_name, function_name, filepath, module_ast
                        )

                        rel = Relationship(
                            source_file=filepath,
                            target_file=target_file,
                            relationship_type=RelationshipType.FUNCTION_CALL,
                            line_number=node.lineno,
                            source_symbol=self._get_call_context(node, module_ast),
                            target_symbol=f"{module_name}.{function_name}",
                            metadata={
                                "call_pattern": "module_qualified",
                                "module_name": module_name,
                                "function_name": function_name,
                            },
                        )
                        relationships.append(rel)
                    # else: Not a module (likely an instance), skip method calls in v0.1.0
                # else: Method chain or nested attribute - skip in v0.1.0
                # These patterns are deferred to v0.1.1/v0.1.2 per DD-1

        return relationships

    def _build_local_function_cache(self, module_ast: ast.Module) -> None:
        """Build cache of locally-defined functions in the current file.

        This cache is used to implement the local scope check in the
        resolution order (TDD Section 3.5.2.2). Only top-level (module-scope)
        functions are cached since nested functions are not accessible from
        outside their enclosing scope.

        Args:
            module_ast: The root AST node of the module.
        """
        self._local_functions.clear()

        # Only collect top-level functions (not nested functions)
        # Nested functions are not accessible at module level
        for node in module_ast.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._local_functions.add(node.name)

    def _resolve_function(self, function_name: str, filepath: str, module_ast: ast.Module) -> str:
        """Resolve a function call to its defining file.

        Implements the resolution order from TDD Section 3.5.2.2:
        1. Local scope: Check if function defined in current file
        2. Imported names: Check if function imported
        3. Built-in functions: Mark as <builtin:name>
        4. Unresolved: Mark as <unresolved:name>

        Args:
            function_name: Name of the function being called.
            filepath: Absolute path to the file containing the call.
            module_ast: The root AST node of the module.

        Returns:
            Resolved file path, or special marker for built-in/unresolved.
        """
        # 1. Local scope: Check if function defined locally
        if function_name in self._local_functions:
            return filepath

        # 2. Imported names: Build import map and check
        if not self._import_map:
            self._build_import_map(module_ast, filepath)

        if function_name in self._import_map:
            return self._import_map[function_name]

        # 3. Built-in functions
        if function_name in self.BUILTIN_FUNCTIONS:
            return f"<builtin:{function_name}>"

        # 4. Unresolved
        return f"<unresolved:{function_name}>"

    def _resolve_module_qualified_call(
        self, module_name: str, function_name: str, filepath: str, module_ast: ast.Module
    ) -> str:
        """Resolve a module-qualified function call.

        For calls like module.function(), resolve to the file where function is defined.

        Args:
            module_name: Name of the module (e.g., 'utils').
            function_name: Name of the function (e.g., 'helper').
            filepath: Absolute path to the file containing the call.
            module_ast: The root AST node of the module.

        Returns:
            Resolved file path, or special marker for unresolved.
        """
        # Build import map if not already built
        if not self._import_map:
            self._build_import_map(module_ast, filepath)

        # Check if module_name is an imported module
        if module_name in self._import_map:
            module_file = self._import_map[module_name]

            # If it's a real file (not <stdlib:> or <third-party:>), return it
            if not module_file.startswith("<"):
                return module_file

            # For stdlib/third-party modules, mark as such
            if module_file.startswith("<stdlib:"):
                return f"<stdlib:{module_name}.{function_name}>"
            elif module_file.startswith("<third-party:"):
                return f"<third-party:{module_name}.{function_name}>"

        # Unresolved
        return f"<unresolved:{module_name}.{function_name}>"

    def _build_import_map(self, module_ast: ast.Module, filepath: str) -> None:
        """Build a map of imported names to their source files.

        This method extracts import information from the AST to build a map
        that can be used for function resolution. It relies on the same
        module resolution logic as ImportDetector.

        Note: In a full implementation, this would ideally use the relationships
        already extracted by ImportDetector. For v0.1.0, we re-parse imports
        to keep detectors independent and stateless.

        Args:
            module_ast: The root AST node of the module.
            filepath: Absolute path to the file being analyzed.
        """
        self._import_map.clear()

        # We need to import ImportDetector to use its resolution logic
        from .import_detector import ImportDetector

        import_detector = ImportDetector()

        for node in ast.walk(module_ast):
            # Handle 'import module' statements
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name
                    target_file = import_detector._resolve_module(module_name, filepath)

                    # Use alias if provided, otherwise use module name
                    import_name = alias.asname if alias.asname else alias.name
                    self._import_map[import_name] = target_file

            # Handle 'from module import name' statements
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module if node.module else ""
                level = node.level if node.level else 0

                for alias in node.names:
                    # Skip wildcard imports (cannot track specific names)
                    if alias.name == "*":
                        continue

                    # For relative imports with no module (e.g., 'from . import utils')
                    if level > 0 and not module_name:
                        actual_module_name = alias.name if alias.name != "*" else ""
                    else:
                        actual_module_name = module_name

                    # Resolve module path
                    if level > 0:
                        target_file = import_detector._resolve_relative_import(
                            actual_module_name, filepath, level
                        )
                    else:
                        target_file = import_detector._resolve_module(actual_module_name, filepath)

                    # Use alias if provided, otherwise use imported name
                    import_name = alias.asname if alias.asname else alias.name
                    self._import_map[import_name] = target_file

    def _get_call_context(self, call_node: ast.Call, module_ast: ast.Module) -> Optional[str]:
        """Get the context where a function call occurs.

        Returns a string describing where the call happens (e.g., "in function foo",
        "in class Bar", "at module level").

        Args:
            call_node: The Call AST node.
            module_ast: The root AST node of the module.

        Returns:
            Context string, or None if at module level.
        """
        # Find the enclosing function or class
        # This is a simplified implementation; a full implementation would
        # maintain a context stack during traversal

        # First check for functions (more specific than classes)
        closest_function = None
        for node in ast.walk(module_ast):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and self._is_node_inside(call_node, node)
                and (
                    closest_function is None
                    or (
                        hasattr(node, "lineno")
                        and hasattr(closest_function, "lineno")
                        and node.lineno > closest_function.lineno
                    )
                )
            ):
                closest_function = node

        if closest_function:
            return closest_function.name

        # If no function, check for classes
        for node in ast.walk(module_ast):
            if isinstance(node, ast.ClassDef) and self._is_node_inside(call_node, node):
                return f"class {node.name}"

        return None  # Module level

    def _is_node_inside(self, inner: ast.AST, outer: ast.AST) -> bool:
        """Check if inner node is inside outer node.

        Args:
            inner: The potentially inner node.
            outer: The potentially outer node.

        Returns:
            True if inner is inside outer, False otherwise.
        """
        # Simple check based on line numbers
        # Note: This is approximate; a full implementation would use proper AST traversal
        if not hasattr(inner, "lineno") or not hasattr(outer, "lineno"):
            return False

        inner_line: int = inner.lineno
        outer_start: int = outer.lineno

        # Get the end line of the outer node
        outer_end: int = outer.end_lineno if hasattr(outer, "end_lineno") else outer_start

        return bool(outer_start <= inner_line <= outer_end)

    def priority(self) -> int:
        """Return detector priority.

        FunctionCallDetector has medium priority (50) as it's a core detector
        that relies on ImportDetector (priority 100) to have run first.

        Returns:
            Priority value (50).
        """
        return 50

    def name(self) -> str:
        """Return detector name.

        Returns:
            Detector name: "FunctionCallDetector".
        """
        return "FunctionCallDetector"
