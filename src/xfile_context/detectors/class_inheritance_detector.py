# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Class inheritance relationship detector plugin.

This module implements the ClassInheritanceDetector plugin that detects class
inheritance relationships in Python code and resolves parent classes to defining files.

v0.1.0 Scope (TDD Section 3.5.2.3):
- Single inheritance: class Child(Parent)
- Multiple inheritance: class Child(Parent1, Parent2)
- Nested inheritance: class Child(package.module.Parent)

Parent Class Resolution:
1. Local scope: Check if parent class defined in current file
2. Imported names: Resolve via import tracking from ImportDetector
3. Built-in classes: Mark as <builtin:name>
4. Unresolved: Mark as <unresolved:name>

See TDD Section 3.5.2.3 for detailed specifications.
"""

import ast
import builtins
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from xfile_context.detectors.base import RelationshipDetector
from xfile_context.models import (
    ReferenceType,
    Relationship,
    RelationshipType,
    SymbolDefinition,
    SymbolReference,
    SymbolType,
)

logger = logging.getLogger(__name__)


class ClassInheritanceDetector(RelationshipDetector):
    """Detector for class inheritance relationships in Python code.

    Detects class definitions with parent classes and resolves them to defining
    files when possible. Implements the detector plugin pattern from DD-1.

    Patterns Detected (v0.1.0):
    - Single inheritance: class Child(Parent)
    - Multiple inheritance: class Child(Parent1, Parent2)
    - Nested inheritance: class Child(package.module.Parent)

    Parent Class Resolution:
    1. Local scope: Check if class defined in current file
    2. Imported names: Use import relationships to resolve
    3. Built-in classes: Mark as <builtin:name>
    4. Unresolved: Mark as <unresolved:name>

    Priority: 50 (Core detector - runs after foundation detectors like ImportDetector)

    See TDD Section 3.4.4 for detector interface specifications.
    """

    # Python built-in exception and base classes
    # Computed at module import time for performance
    # Includes all types from builtins: Exception, ValueError, dict, list, etc.
    BUILTIN_CLASSES = frozenset(
        name for name in dir(builtins) if isinstance(getattr(builtins, name), type)
    )

    def __init__(self) -> None:
        """Initialize the detector.

        Note: Detector instances are reused across multiple files (per DetectorRegistry design).
        Caches are built once per file and invalidated when analyzing a different file.
        """
        # Cache for local class definitions (per-file cache)
        self._local_classes: Set[str] = set()
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
        """Detect class inheritance relationships in an AST node.

        Args:
            node: AST node to analyze.
            filepath: Absolute path to the file being analyzed.
            module_ast: The root AST node of the entire module (for context).

        Returns:
            List of detected inheritance relationships. Empty list if no inheritance found.
        """
        relationships: List[Relationship] = []

        # Handle class definitions with inheritance
        if isinstance(node, ast.ClassDef):
            # Build caches if analyzing a new file (invalidate cache on file change)
            # This prevents cache pollution when the same detector instance
            # is reused across multiple files (DetectorRegistry pattern)
            if self._cached_filepath != filepath:
                self._cached_filepath = filepath
                self._local_classes.clear()
                self._import_map.clear()
                self._build_local_class_cache(module_ast)

            # Check if class has any base classes (inheritance)
            if node.bases:
                child_class = node.name

                # Process each parent class in order
                for idx, base in enumerate(node.bases):
                    parent_name = self._extract_parent_name(base)
                    if parent_name:
                        target_file = self._resolve_parent_class(
                            parent_name, base, filepath, module_ast
                        )

                        metadata: Dict[str, Any] = {
                            "child_class": child_class,
                            "parent_class": parent_name,
                            "inheritance_order": idx,
                            "total_parents": len(node.bases),
                        }

                        rel = Relationship(
                            source_file=filepath,
                            target_file=target_file,
                            relationship_type=RelationshipType.CLASS_INHERITANCE,
                            line_number=node.lineno,
                            source_symbol=child_class,
                            target_symbol=parent_name,
                            metadata=metadata,
                        )
                        relationships.append(rel)

        return relationships

    def _extract_parent_name(self, base_node: ast.expr) -> Optional[str]:
        """Extract parent class name from a base class node.

        Handles:
        - Simple name: Parent -> "Parent"
        - Attribute: module.Parent -> "module.Parent"
        - Nested attribute: pkg.module.Parent -> "pkg.module.Parent"

        Args:
            base_node: AST node representing the base class.

        Returns:
            Parent class name as string, or None if cannot be extracted.
        """
        if isinstance(base_node, ast.Name):
            # Simple inheritance: class Child(Parent)
            return base_node.id
        elif isinstance(base_node, ast.Attribute):
            # Nested inheritance: class Child(module.Parent)
            # Build the full name by traversing the attribute chain
            parts = []
            current: ast.expr = base_node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
                # Reverse to get correct order (module.Parent)
                return ".".join(reversed(parts))
        return None

    def _build_local_class_cache(self, module_ast: ast.Module) -> None:
        """Build cache of locally-defined classes in the current file.

        This cache is used to implement the local scope check in the
        resolution order. Only top-level (module-scope) classes are cached
        since nested classes require qualification (e.g., Outer.Inner).

        Args:
            module_ast: The root AST node of the module.
        """
        self._local_classes.clear()

        # Only collect top-level classes (not nested classes)
        # Nested classes like Outer.Inner are not directly accessible
        # and should be resolved as unresolved or via qualified names
        for node in module_ast.body:
            if isinstance(node, ast.ClassDef):
                self._local_classes.add(node.name)

    def _resolve_parent_class(
        self, parent_name: str, base_node: ast.expr, filepath: str, module_ast: ast.Module
    ) -> str:
        """Resolve a parent class to its defining file.

        Implements the resolution order:
        1. Local scope: Check if class defined in current file
        2. Imported names: Check if class imported
        3. Built-in classes: Mark as <builtin:name>
        4. Unresolved: Mark as <unresolved:name>

        Args:
            parent_name: Name of the parent class (may include module prefix).
            base_node: AST node representing the base class.
            filepath: Absolute path to the file containing the inheritance.
            module_ast: The root AST node of the module.

        Returns:
            Resolved file path, or special marker for built-in/unresolved.
        """
        # Handle nested names (e.g., module.Parent)
        if "." in parent_name:
            # Split into module and class parts
            parts = parent_name.split(".")
            module_part = ".".join(parts[:-1])

            # Build import map if not already built
            if not self._import_map:
                self._build_import_map(module_ast, filepath)

            # Check if module is imported
            if module_part in self._import_map:
                module_file = self._import_map[module_part]

                # If it's a real file (not <stdlib:> or <third-party:>), return it
                if not module_file.startswith("<"):
                    return module_file

                # For stdlib/third-party modules, mark as such
                if module_file.startswith("<stdlib:"):
                    return f"<stdlib:{parent_name}>"
                elif module_file.startswith("<third-party:"):
                    return f"<third-party:{parent_name}>"

            # Unresolved nested name
            return f"<unresolved:{parent_name}>"

        # Simple name (no dots) - apply standard resolution order
        # 1. Local scope: Check if class defined locally
        if parent_name in self._local_classes:
            return filepath

        # 2. Imported names: Build import map and check
        if not self._import_map:
            self._build_import_map(module_ast, filepath)

        if parent_name in self._import_map:
            return self._import_map[parent_name]

        # 3. Built-in classes
        if parent_name in self.BUILTIN_CLASSES:
            return f"<builtin:{parent_name}>"

        # 4. Unresolved
        return f"<unresolved:{parent_name}>"

    def _build_import_map(self, module_ast: ast.Module, filepath: str) -> None:
        """Build a map of imported names to their source files.

        This method extracts import information from the AST to build a map
        that can be used for parent class resolution. It relies on the same
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
        from xfile_context.detectors.import_detector import ImportDetector

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

    def priority(self) -> int:
        """Return detector priority.

        ClassInheritanceDetector has medium priority (50) as it's a core detector
        that relies on ImportDetector (priority 100) to have run first.

        Returns:
            Priority value (50).
        """
        return 50

    def name(self) -> str:
        """Return detector name.

        Returns:
            Detector name: "ClassInheritanceDetector".
        """
        return "ClassInheritanceDetector"

    def supports_symbol_extraction(self) -> bool:
        """Check if this detector supports symbol extraction mode.

        Returns:
            True - ClassInheritanceDetector supports symbol extraction.
        """
        return True

    def extract_symbols(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
    ) -> Tuple[List[SymbolDefinition], List[SymbolReference]]:
        """Extract class definitions and parent class references (Issue #122).

        ClassInheritanceDetector produces both:
        - Definitions: Class definitions found in the file
        - References: Parent class references (inheritance relationships)

        Args:
            node: AST node to analyze.
            filepath: Absolute path to the file being analyzed.
            module_ast: The root AST node of the entire module (for context).

        Returns:
            Tuple of (definitions, references) for class inheritance patterns.
        """
        definitions: List[SymbolDefinition] = []
        references: List[SymbolReference] = []

        if isinstance(node, ast.ClassDef):
            # Build caches if analyzing a new file
            if self._cached_filepath != filepath:
                self._cached_filepath = filepath
                self._local_classes.clear()
                self._import_map.clear()
                self._build_local_class_cache(module_ast)

            # Extract class definition
            line_end: int = node.end_lineno if node.end_lineno else node.lineno

            # Get decorator names
            decorators = None
            if node.decorator_list:
                decorators = []
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name):
                        decorators.append(dec.id)
                    elif isinstance(dec, ast.Attribute):
                        decorators.append(self._extract_parent_name(dec) or "")
                    elif isinstance(dec, ast.Call):
                        # Decorator with arguments: @decorator(args)
                        if isinstance(dec.func, ast.Name):
                            decorators.append(dec.func.id)
                        elif isinstance(dec.func, ast.Attribute):
                            decorators.append(self._extract_parent_name(dec.func) or "")

            # Get base class names
            bases = None
            if node.bases:
                bases = []
                for base in node.bases:
                    base_name = self._extract_parent_name(base)
                    if base_name:
                        bases.append(base_name)

            # Extract docstring if present
            docstring = None
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                # Get first line of docstring
                full_doc = node.body[0].value.value
                docstring = full_doc.split("\n")[0].strip()

            definition = SymbolDefinition(
                name=node.name,
                symbol_type=SymbolType.CLASS,
                line_start=node.lineno,
                line_end=line_end,
                signature=f"class {node.name}",
                decorators=decorators,
                bases=bases,
                docstring=docstring,
            )
            definitions.append(definition)

            # Extract parent class references
            if node.bases:
                for idx, base in enumerate(node.bases):
                    parent_name = self._extract_parent_name(base)
                    if parent_name:
                        resolved_module = self._resolve_parent_class(
                            parent_name, base, filepath, module_ast
                        )

                        # Determine if this is a module-qualified reference
                        module_name = None
                        if "." in parent_name:
                            parts = parent_name.split(".")
                            module_name = ".".join(parts[:-1])

                        ref = SymbolReference(
                            name=parent_name,
                            reference_type=ReferenceType.CLASS_REFERENCE,
                            line_number=node.lineno,
                            resolved_module=resolved_module,
                            resolved_symbol=parent_name.split(".")[-1],  # Just the class name
                            module_name=module_name,
                            metadata={
                                "child_class": node.name,
                                "inheritance_order": str(idx),
                                "total_parents": str(len(node.bases)),
                            },
                        )
                        references.append(ref)

        return (definitions, references)
