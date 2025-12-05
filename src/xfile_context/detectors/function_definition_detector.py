# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Function definition detector plugin.

This module implements the FunctionDefinitionDetector plugin that extracts
SymbolDefinition entries for function and method definitions in Python code.

This detector complements FunctionCallDetector:
- FunctionCallDetector: Produces FUNCTION_CALL references (calls to functions)
- FunctionDefinitionDetector: Produces SymbolDefinition entries (function definitions)

Together, these enable `_get_target_line()` in RelationshipBuilder to resolve
line numbers for function symbols, fixing missing line numbers in injected context.

v0.1.0 Scope:
- Regular functions: def foo(): pass
- Async functions: async def bar(): pass
- Methods inside classes (detected with parent_class field)
- Extracts: name, line range, signature, decorators, docstring

Note: Decorated functions/classes are ALSO handled by DecoratorDetector.
This detector ensures ALL functions get definitions, not just decorated ones.

See TDD Section 3.5.1 for AST parsing pipeline specifications.
See Issue #140 for implementation rationale.
"""

import ast
import logging
from typing import Dict, List, Optional, Tuple

from xfile_context.detectors.base import RelationshipDetector
from xfile_context.models import Relationship, SymbolDefinition, SymbolReference, SymbolType

logger = logging.getLogger(__name__)


class FunctionDefinitionDetector(RelationshipDetector):
    """Detector for function and method definitions in Python code.

    Extracts SymbolDefinition entries for all function definitions, enabling
    line number resolution in RelationshipBuilder._get_target_line().

    Patterns Detected:
    - Regular functions: def foo(): pass
    - Async functions: async def bar(): pass
    - Methods: def method(self): pass (inside classes)
    - Static/class methods (with decorators)

    Note: This detector focuses on DEFINITIONS, not CALLS.
    FunctionCallDetector handles function call references.

    Priority: 50 (Core detector - same as FunctionCallDetector and ClassInheritanceDetector)

    See TDD Section 3.4.4 for detector interface specifications.
    """

    def __init__(self) -> None:
        """Initialize the detector.

        Note: Detector instances are reused across multiple files (per DetectorRegistry design).
        """
        # Cache mapping function node IDs to parent class names (for performance)
        self._parent_class_map: Dict[int, str] = {}
        # Track which file the cache belongs to (for cache invalidation)
        self._cached_filepath: Optional[str] = None

    def detect(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
    ) -> List[Relationship]:
        """Detect function definitions in an AST node.

        FunctionDefinitionDetector does not produce Relationship objects.
        It only produces SymbolDefinition entries via extract_symbols().

        Args:
            node: AST node to analyze.
            filepath: Absolute path to the file being analyzed.
            module_ast: The root AST node of the entire module (for context).

        Returns:
            Empty list - this detector only produces symbol definitions.
        """
        # This detector does not produce relationships, only symbol definitions
        return []

    def priority(self) -> int:
        """Return detector priority.

        FunctionDefinitionDetector has medium priority (50) as it's a core detector.
        Same priority as FunctionCallDetector and ClassInheritanceDetector.

        Returns:
            Priority value (50).
        """
        return 50

    def name(self) -> str:
        """Return detector name.

        Returns:
            Detector name: "FunctionDefinitionDetector".
        """
        return "FunctionDefinitionDetector"

    def supports_symbol_extraction(self) -> bool:
        """Check if this detector supports symbol extraction mode.

        Returns:
            True - FunctionDefinitionDetector supports symbol extraction.
        """
        return True

    def extract_symbols(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
    ) -> Tuple[List[SymbolDefinition], List[SymbolReference]]:
        """Extract function/method definitions from an AST node.

        FunctionDefinitionDetector produces definitions for all functions,
        ensuring line numbers can be resolved for function symbols.

        Args:
            node: AST node to analyze.
            filepath: Absolute path to the file being analyzed.
            module_ast: The root AST node of the entire module (for context).

        Returns:
            Tuple of (definitions, []) - functions produce definitions, not references.
        """
        definitions: List[SymbolDefinition] = []

        # Invalidate cache on file change and rebuild parent class map
        if self._cached_filepath != filepath:
            self._cached_filepath = filepath
            self._parent_class_map.clear()
            self._build_parent_class_map(module_ast)

        # Handle function definitions (regular and async)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            definition = self._extract_function_definition(node)
            if definition:
                definitions.append(definition)

        return (definitions, [])

    def _extract_function_definition(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> Optional[SymbolDefinition]:
        """Extract a SymbolDefinition from a function/method node.

        Args:
            node: FunctionDef or AsyncFunctionDef AST node.

        Returns:
            SymbolDefinition for the function, or None if extraction fails.
        """
        # Determine line range
        line_end: int = node.end_lineno if node.end_lineno else node.lineno

        # Build function signature
        signature = self._build_signature(node)

        # Extract decorator names
        decorators = self._extract_decorators(node)

        # Extract docstring (first line only)
        docstring = self._extract_docstring(node)

        # Determine parent class (if this is a method) using pre-built cache
        parent_class = self._find_parent_class(node)

        return SymbolDefinition(
            name=node.name,
            symbol_type=SymbolType.FUNCTION,
            line_start=node.lineno,
            line_end=line_end,
            signature=signature,
            decorators=decorators,
            docstring=docstring,
            parent_class=parent_class,
        )

    def _build_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Build function signature string.

        Args:
            node: FunctionDef or AsyncFunctionDef AST node.

        Returns:
            Signature string like "def foo(a, b)" or "async def bar(x)".
        """
        # Collect all argument names
        args_list: List[str] = []

        # Regular positional args
        for arg in node.args.args:
            args_list.append(arg.arg)

        # *args
        if node.args.vararg:
            args_list.append(f"*{node.args.vararg.arg}")

        # Keyword-only args
        for arg in node.args.kwonlyargs:
            args_list.append(arg.arg)

        # **kwargs
        if node.args.kwarg:
            args_list.append(f"**{node.args.kwarg.arg}")

        args_str = ", ".join(args_list)
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"

        return f"{prefix} {node.name}({args_str})"

    def _extract_decorators(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> Optional[List[str]]:
        """Extract decorator names from a function node.

        Args:
            node: FunctionDef or AsyncFunctionDef AST node.

        Returns:
            List of decorator names, or None if no decorators.
        """
        if not node.decorator_list:
            return None

        decorators: List[str] = []
        for decorator in node.decorator_list:
            dec_name = self._get_decorator_name(decorator)
            if dec_name:
                decorators.append(dec_name)

        return decorators if decorators else None

    def _get_decorator_name(self, decorator: ast.expr, depth: int = 0) -> Optional[str]:
        """Get the name of a decorator with recursion protection.

        Args:
            decorator: Decorator AST node.
            depth: Current recursion depth (for safety).

        Returns:
            Decorator name as string, or None if cannot determine.
        """
        # Protection against stack overflow from malicious deep nesting
        max_decorator_depth = 100
        if depth > max_decorator_depth:
            logger.warning(f"Decorator nesting exceeds maximum depth ({max_decorator_depth})")
            return None

        # Simple decorator: @name
        if isinstance(decorator, ast.Name):
            return decorator.id

        # Decorator with arguments: @name(args)
        if isinstance(decorator, ast.Call):
            return self._get_decorator_name(decorator.func, depth + 1)

        # Attribute decorator: @module.name
        if isinstance(decorator, ast.Attribute):
            base_name = self._get_decorator_name(decorator.value, depth + 1)
            if base_name:
                return f"{base_name}.{decorator.attr}"
            return decorator.attr

        return None

    def _extract_docstring(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> Optional[str]:
        """Extract the first line of a function's docstring.

        Args:
            node: FunctionDef or AsyncFunctionDef AST node.

        Returns:
            First line of docstring, or None if no docstring.
        """
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            full_doc = node.body[0].value.value
            return full_doc.split("\n")[0].strip()

        return None

    def _build_parent_class_map(self, module_ast: ast.Module) -> None:
        """Build cache mapping function node IDs to parent class names.

        This pre-computes parent classes in O(m) time instead of O(n*m),
        preventing performance degradation on large files.

        Args:
            module_ast: The root AST node of the module.
        """
        for node in ast.walk(module_ast):
            if isinstance(node, ast.ClassDef):
                # Map each direct method to its parent class
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self._parent_class_map[id(child)] = node.name

    def _find_parent_class(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> Optional[str]:
        """Find the parent class if this function is a method.

        Uses pre-built cache for O(1) lookup instead of O(m) tree traversal.

        Args:
            func_node: The function node to check.

        Returns:
            Parent class name if this is a method, None otherwise.
        """
        return self._parent_class_map.get(id(func_node))
