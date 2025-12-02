# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Warning emission and formatting module.

This module implements structured warning formatting per TDD Section 3.9.3:
- JSON format with all required fields (FR-38)
- Human-readable display format
- Actionable guidance for each pattern type

Warning Format (FR-38):
- type: Pattern identifier (dynamic_dispatch, monkey_patching, exec_eval, decorator, metaclass)
- file: Absolute file path
- line: Line number where pattern detected
- column: Column offset (optional)
- severity: "warning" or "info"
- pattern: Code snippet showing the detected pattern
- message: Human-readable summary
- explanation: Longer explanation with context and guidance (optional)
- timestamp: ISO 8601 timestamp

Related Requirements:
- FR-38 (structured warning format)
- T-6.7 (warning message format test)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .detectors.dynamic_pattern_detector import DynamicPatternType, DynamicPatternWarning

logger = logging.getLogger(__name__)


# Actionable guidance messages per TDD Section 3.9.3
PATTERN_GUIDANCE: Dict[DynamicPatternType, str] = {
    DynamicPatternType.DYNAMIC_DISPATCH: (
        "Consider using explicit function calls if the function name is known. "
        "Dynamic dispatch prevents static analysis of the call target."
    ),
    DynamicPatternType.MONKEY_PATCHING: (
        "Monkey patching modifies module attributes at runtime, making static "
        "analysis unreliable. Consider using dependency injection or explicit "
        "configuration instead."
    ),
    DynamicPatternType.EXEC_EVAL: (
        "Consider using safer alternatives (importlib, ast.literal_eval, or explicit logic). "
        "exec() and eval() execute arbitrary code that cannot be statically analyzed."
    ),
    DynamicPatternType.DECORATOR: (
        "Decorators may modify function behavior in ways that cannot be statically analyzed. "
        "The decorated function's actual implementation may differ from its definition."
    ),
    DynamicPatternType.METACLASS: (
        "Custom metaclasses can dynamically modify class creation. Consider documenting "
        "the metaclass behavior to help with code understanding."
    ),
}

# Human-readable pattern type names
PATTERN_DISPLAY_NAMES: Dict[DynamicPatternType, str] = {
    DynamicPatternType.DYNAMIC_DISPATCH: "Dynamic dispatch",
    DynamicPatternType.MONKEY_PATCHING: "Monkey patching",
    DynamicPatternType.EXEC_EVAL: "exec/eval usage",
    DynamicPatternType.DECORATOR: "Decorator pattern",
    DynamicPatternType.METACLASS: "Metaclass usage",
}


@dataclass
class StructuredWarning:
    """A fully structured warning with all required fields per FR-38.

    This extends DynamicPatternWarning with additional fields needed for
    JSON serialization and human-readable display.

    Attributes:
        type: Pattern identifier (e.g., "dynamic_dispatch")
        file: Absolute file path
        line: Line number where pattern detected
        column: Column offset (optional)
        severity: "warning" or "info"
        pattern: Code snippet showing the detected pattern
        message: Human-readable summary
        explanation: Longer explanation with guidance (optional)
        timestamp: ISO 8601 timestamp of detection
        is_test_module: Whether pattern is in a test module
        metadata: Additional pattern-specific metadata
    """

    type: str
    file: str
    line: int
    severity: str
    pattern: str
    message: str
    timestamp: str
    column: Optional[int] = None
    explanation: Optional[str] = None
    is_test_module: bool = False
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary.

        Returns:
            Dictionary with all fields, excluding None values for optional fields.
        """
        result: Dict[str, Any] = {
            "type": self.type,
            "file": self.file,
            "line": self.line,
            "severity": self.severity,
            "pattern": self.pattern,
            "message": self.message,
            "timestamp": self.timestamp,
        }

        if self.column is not None:
            result["column"] = self.column
        if self.explanation is not None:
            result["explanation"] = self.explanation
        if self.metadata:
            result["metadata"] = self.metadata

        return result

    def to_json(self, indent: Optional[int] = None) -> str:
        """Convert to JSON string.

        Args:
            indent: Optional indentation level for pretty printing.

        Returns:
            JSON string representation of the warning.
        """
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StructuredWarning":
        """Create StructuredWarning from dictionary.

        Args:
            data: Dictionary containing warning fields.

        Returns:
            StructuredWarning instance.

        Raises:
            KeyError: If required fields are missing.
        """
        return cls(
            type=data["type"],
            file=data["file"],
            line=data["line"],
            severity=data["severity"],
            pattern=data["pattern"],
            message=data["message"],
            timestamp=data["timestamp"],
            column=data.get("column"),
            explanation=data.get("explanation"),
            is_test_module=data.get("is_test_module", False),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "StructuredWarning":
        """Create StructuredWarning from JSON string.

        Args:
            json_str: JSON string representation of warning.

        Returns:
            StructuredWarning instance.

        Raises:
            json.JSONDecodeError: If JSON is invalid.
            KeyError: If required fields are missing.
        """
        return cls.from_dict(json.loads(json_str))


class WarningFormatter:
    """Formats warnings for output in various formats.

    Provides methods for:
    - Converting DynamicPatternWarning to StructuredWarning
    - JSON serialization
    - Human-readable display
    - Adding actionable guidance
    """

    @staticmethod
    def format_warning(
        warning: DynamicPatternWarning,
        code_snippet: Optional[str] = None,
        column: Optional[int] = None,
        timestamp: Optional[str] = None,
    ) -> StructuredWarning:
        """Convert DynamicPatternWarning to StructuredWarning.

        Args:
            warning: The DynamicPatternWarning to convert.
            code_snippet: Optional code snippet showing the pattern.
                         If not provided, derived from metadata if available.
            column: Optional column offset.
            timestamp: Optional ISO 8601 timestamp. If not provided, uses current time.

        Returns:
            StructuredWarning with all required fields populated.
        """
        # Generate timestamp if not provided
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        # Determine code snippet from metadata if not provided
        if code_snippet is None:
            code_snippet = WarningFormatter._derive_code_snippet(warning)

        # Get actionable guidance for this pattern type
        explanation = PATTERN_GUIDANCE.get(warning.pattern_type)

        # Generate human-readable message
        display_name = PATTERN_DISPLAY_NAMES.get(warning.pattern_type, warning.pattern_type.value)
        message = f"{display_name} detected - relationship tracking unavailable"

        return StructuredWarning(
            type=warning.pattern_type.value,
            file=warning.filepath,
            line=warning.line_number,
            column=column,
            severity=warning.severity.value,
            pattern=code_snippet,
            message=message,
            explanation=explanation,
            timestamp=timestamp,
            is_test_module=warning.is_test_module,
            metadata=warning.metadata or {},
        )

    @staticmethod
    def _derive_code_snippet(warning: DynamicPatternWarning) -> str:
        """Derive code snippet from warning metadata.

        Args:
            warning: The DynamicPatternWarning.

        Returns:
            Code snippet string derived from metadata.
        """
        metadata = warning.metadata or {}
        pattern_type = warning.pattern_type

        if pattern_type == DynamicPatternType.DYNAMIC_DISPATCH:
            obj_name = metadata.get("object_name", "obj")
            attr_var = metadata.get("attribute_variable", "attr")
            return f"getattr({obj_name}, {attr_var})"

        elif pattern_type == DynamicPatternType.MONKEY_PATCHING:
            target = metadata.get("target", "module.attr")
            return f"{target} = <replacement>"

        elif pattern_type == DynamicPatternType.EXEC_EVAL:
            call_type = metadata.get("call_type", "exec")
            return f"{call_type}(...)"

        elif pattern_type == DynamicPatternType.DECORATOR:
            decorator_name = metadata.get("decorator_name", "decorator")
            # Strip @ if already present to avoid double-@
            decorator_name = decorator_name.lstrip("@")
            return f"@{decorator_name}"

        elif pattern_type == DynamicPatternType.METACLASS:
            metaclass_name = metadata.get("metaclass_name", "Meta")
            class_name = metadata.get("class_name", "Class")
            return f"class {class_name}(metaclass={metaclass_name})"

        # Fallback
        return f"<{pattern_type.value}>"

    @staticmethod
    def format_human_readable(warning: StructuredWarning) -> str:
        """Format warning for human-readable display.

        Format per TDD Section 3.9.3:
        ⚠️ src/module.py:42 - Dynamic dispatch detected
          getattr(obj, 'method')()
          → Relationship tracking unavailable for dynamic function calls

        Args:
            warning: StructuredWarning to format.

        Returns:
            Human-readable string representation.
        """
        # Determine prefix based on severity
        prefix = "⚠️" if warning.severity == "warning" else "ℹ️"

        # Extract filename from path for display
        filepath = warning.file
        # Use relative-style display if path is long
        if len(filepath) > 50:
            filepath = "..." + filepath[-47:]

        # Build location string
        location = f"{filepath}:{warning.line}"
        if warning.column is not None:
            location += f":{warning.column}"

        # Get display name for pattern type
        pattern_type_enum = DynamicPatternType(warning.type)
        display_name = PATTERN_DISPLAY_NAMES.get(pattern_type_enum, warning.type)

        # Build output lines
        lines = [
            f"{prefix} {location} - {display_name} detected",
            f"  {warning.pattern}",
        ]

        # Add guidance if available
        if warning.explanation:
            # Truncate explanation for display (first sentence)
            explanation = warning.explanation.split(".")[0]
            lines.append(f"  → {explanation}")

        return "\n".join(lines)

    @staticmethod
    def format_json_batch(warnings: List[StructuredWarning], indent: int = 2) -> str:
        """Format multiple warnings as a JSON array.

        Args:
            warnings: List of StructuredWarnings to format.
            indent: Indentation level for pretty printing.

        Returns:
            JSON array string of warnings.
        """
        return json.dumps([w.to_dict() for w in warnings], indent=indent)


class WarningEmitter:
    """Service for collecting and emitting warnings during analysis.

    This is the central service for warning management during file analysis.
    It collects warnings from detectors and provides methods to:
    - Aggregate warnings across multiple files/detectors
    - Emit warnings to logger
    - Export warnings in JSON or human-readable format

    Usage:
        emitter = WarningEmitter()
        # After detection phase
        for detector in detectors:
            emitter.add_warnings(detector.get_warnings())
        # Get formatted output
        json_output = emitter.to_json()
        human_output = emitter.to_human_readable()
    """

    def __init__(self) -> None:
        """Initialize the warning emitter."""
        self._warnings: List[StructuredWarning] = []
        self._formatter = WarningFormatter()

    def add_warning(
        self,
        warning: DynamicPatternWarning,
        code_snippet: Optional[str] = None,
        column: Optional[int] = None,
    ) -> None:
        """Add a single warning.

        Args:
            warning: DynamicPatternWarning from a detector.
            code_snippet: Optional code snippet for the pattern.
            column: Optional column offset.
        """
        structured = self._formatter.format_warning(
            warning, code_snippet=code_snippet, column=column
        )
        self._warnings.append(structured)

    def add_warnings(
        self,
        warnings: List[DynamicPatternWarning],
        code_snippets: Optional[Dict[int, str]] = None,
    ) -> None:
        """Add multiple warnings from a detector.

        Args:
            warnings: List of DynamicPatternWarning from a detector.
            code_snippets: Optional dict mapping line numbers to code snippets.
        """
        code_snippets = code_snippets or {}
        for warning in warnings:
            snippet = code_snippets.get(warning.line_number)
            self.add_warning(warning, code_snippet=snippet)

    def get_warnings(self, include_test_modules: bool = False) -> List[StructuredWarning]:
        """Get collected warnings.

        Args:
            include_test_modules: If True, include warnings from test modules.
                                  Default is False (suppressed per TDD Section 3.9.1).

        Returns:
            List of StructuredWarning objects.
        """
        if include_test_modules:
            return self._warnings.copy()
        return [w for w in self._warnings if not w.is_test_module]

    def get_warnings_by_file(
        self, filepath: str, include_test_modules: bool = False
    ) -> List[StructuredWarning]:
        """Get warnings for a specific file.

        Args:
            filepath: File path to filter by.
            include_test_modules: If True, include warnings from test modules.

        Returns:
            List of StructuredWarning objects for the specified file.
        """
        warnings = self.get_warnings(include_test_modules=include_test_modules)
        return [w for w in warnings if w.file == filepath]

    def get_warnings_by_type(
        self, pattern_type: DynamicPatternType, include_test_modules: bool = False
    ) -> List[StructuredWarning]:
        """Get warnings of a specific pattern type.

        Args:
            pattern_type: DynamicPatternType to filter by.
            include_test_modules: If True, include warnings from test modules.

        Returns:
            List of StructuredWarning objects of the specified type.
        """
        warnings = self.get_warnings(include_test_modules=include_test_modules)
        return [w for w in warnings if w.type == pattern_type.value]

    def to_json(self, include_test_modules: bool = False, indent: int = 2) -> str:
        """Export warnings as JSON.

        Args:
            include_test_modules: If True, include warnings from test modules.
            indent: Indentation level for pretty printing.

        Returns:
            JSON string of warnings array.
        """
        warnings = self.get_warnings(include_test_modules=include_test_modules)
        return WarningFormatter.format_json_batch(warnings, indent=indent)

    def to_human_readable(self, include_test_modules: bool = False) -> str:
        """Export warnings as human-readable text.

        Args:
            include_test_modules: If True, include warnings from test modules.

        Returns:
            Human-readable string with all warnings.
        """
        warnings = self.get_warnings(include_test_modules=include_test_modules)
        if not warnings:
            return "No warnings detected."

        lines = []
        for warning in warnings:
            lines.append(WarningFormatter.format_human_readable(warning))
            lines.append("")  # Empty line between warnings

        return "\n".join(lines).strip()

    def emit_to_logger(self, include_test_modules: bool = False) -> None:
        """Emit all warnings to the logger.

        Args:
            include_test_modules: If True, include warnings from test modules.
        """
        warnings = self.get_warnings(include_test_modules=include_test_modules)
        for warning in warnings:
            formatted = WarningFormatter.format_human_readable(warning)
            if warning.severity == "warning":
                logger.warning(formatted)
            else:
                logger.info(formatted)

    def clear(self) -> None:
        """Clear all collected warnings."""
        self._warnings.clear()

    def count(self, include_test_modules: bool = False) -> int:
        """Get count of collected warnings.

        Args:
            include_test_modules: If True, include warnings from test modules.

        Returns:
            Number of warnings.
        """
        return len(self.get_warnings(include_test_modules=include_test_modules))

    def summary(self, include_test_modules: bool = False) -> Dict[str, int]:
        """Get summary of warnings by type.

        Args:
            include_test_modules: If True, include warnings from test modules.

        Returns:
            Dictionary mapping pattern types to counts.
        """
        warnings = self.get_warnings(include_test_modules=include_test_modules)
        summary: Dict[str, int] = {}
        for warning in warnings:
            summary[warning.type] = summary.get(warning.type, 0) + 1
        return summary
