# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Warning suppression configuration and filtering.

This module implements warning suppression per TDD Section 3.9.4:
- File-level suppression (FR-39)
- Directory-level suppression with glob patterns (FR-40)
- Pattern-type suppression (global)
- Per-file pattern-type suppression (advanced)

Suppression Precedence (most specific wins):
1. File-specific pattern-type suppression
2. Global pattern-type suppression
3. File-level suppression
4. Directory-level suppression
5. Test vs source module detection (built-in)

Related Requirements:
- FR-39 (file-level suppression)
- FR-40 (directory-level suppression)
- T-6.8 (warning suppression test)
"""

import fnmatch
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from xfile_context.warning_formatter import StructuredWarning

logger = logging.getLogger(__name__)

# Valid pattern type names for configuration
VALID_PATTERN_TYPES: Set[str] = {
    "dynamic_dispatch",
    "monkey_patching",
    "exec_eval",
    "decorator",
    "metaclass",
}


class WarningSuppressionManager:
    """Manages warning suppression based on configuration.

    This class evaluates whether warnings should be suppressed based on:
    - File/directory patterns in suppress_warnings config
    - Global pattern-type suppression flags
    - Per-file pattern-type suppressions

    Usage:
        config = Config()
        suppression = WarningSuppressionManager(config)
        if suppression.should_suppress(warning):
            # Warning is suppressed, don't emit
            pass

    Attributes:
        suppress_patterns: List of file/directory glob patterns to suppress
        global_pattern_suppressions: Dict mapping pattern types to suppression flag
        file_specific_suppressions: Dict mapping file paths to list of suppressed pattern types
        project_root: Optional project root for resolving relative paths
    """

    def __init__(
        self,
        suppress_patterns: Optional[List[str]] = None,
        global_pattern_suppressions: Optional[Dict[str, bool]] = None,
        file_specific_suppressions: Optional[Dict[str, List[str]]] = None,
        project_root: Optional[Path] = None,
    ) -> None:
        """Initialize the suppression manager.

        Args:
            suppress_patterns: List of file/directory patterns to suppress warnings for.
                              Supports glob patterns like "tests/**/*" or exact paths.
            global_pattern_suppressions: Dict mapping pattern type names to suppression flags.
                                        Example: {"dynamic_dispatch": True, "metaclass": False}
            file_specific_suppressions: Dict mapping file paths to list of pattern types
                                        to suppress for that specific file.
                                        Example: {"src/utils.py": ["dynamic_dispatch", "decorator"]}
            project_root: Optional project root for resolving relative paths.
                         If not provided, uses current working directory.
        """
        self.suppress_patterns = suppress_patterns or []
        self.project_root = project_root or Path.cwd()

        # Validate and store global pattern suppressions
        self.global_pattern_suppressions: Dict[str, bool] = {}
        if global_pattern_suppressions:
            self._validate_and_store_global_suppressions(global_pattern_suppressions)

        # Validate and store file-specific suppressions
        self.file_specific_suppressions: Dict[str, List[str]] = {}
        if file_specific_suppressions:
            self._validate_and_store_file_specific_suppressions(file_specific_suppressions)

        # Log configuration summary
        self._log_configuration_summary()

    def _validate_and_store_global_suppressions(self, suppressions: Dict[str, bool]) -> None:
        """Validate and store global pattern suppressions.

        Args:
            suppressions: Dict mapping pattern type names to suppression flags.
        """
        for pattern_type, suppress in suppressions.items():
            if pattern_type not in VALID_PATTERN_TYPES:
                logger.warning(
                    f"Invalid pattern type '{pattern_type}' in global suppressions, ignoring. "
                    f"Valid types: {VALID_PATTERN_TYPES}"
                )
                continue

            if not isinstance(suppress, bool):
                logger.warning(
                    f"Invalid suppression value for '{pattern_type}': {suppress}, "
                    f"expected bool, ignoring"
                )
                continue

            self.global_pattern_suppressions[pattern_type] = suppress

    def _validate_and_store_file_specific_suppressions(
        self, suppressions: Dict[str, List[str]]
    ) -> None:
        """Validate and store file-specific suppressions.

        Args:
            suppressions: Dict mapping file paths to list of pattern types to suppress.
        """
        for filepath, pattern_types in suppressions.items():
            if not isinstance(pattern_types, list):
                logger.warning(
                    f"Invalid suppression config for '{filepath}': expected list of pattern types, "
                    f"got {type(pattern_types).__name__}, ignoring"
                )
                continue

            valid_types: List[str] = []
            for pattern_type in pattern_types:
                if pattern_type not in VALID_PATTERN_TYPES:
                    logger.warning(
                        f"Invalid pattern type '{pattern_type}' for file '{filepath}', ignoring. "
                        f"Valid types: {VALID_PATTERN_TYPES}"
                    )
                    continue
                valid_types.append(pattern_type)

            if valid_types:
                self.file_specific_suppressions[filepath] = valid_types

    def _log_configuration_summary(self) -> None:
        """Log a summary of the suppression configuration."""
        if self.suppress_patterns:
            logger.debug(
                f"Warning suppression patterns configured: {len(self.suppress_patterns)} patterns"
            )
        if self.global_pattern_suppressions:
            enabled = [k for k, v in self.global_pattern_suppressions.items() if v]
            if enabled:
                logger.debug(f"Global pattern suppressions enabled: {enabled}")
        if self.file_specific_suppressions:
            count = len(self.file_specific_suppressions)
            logger.debug(f"File-specific suppressions configured for {count} files")

    @classmethod
    def from_config(
        cls, config: Any, project_root: Optional[Path] = None
    ) -> "WarningSuppressionManager":
        """Create WarningSuppressionManager from Config object.

        This factory method extracts suppression settings from a Config object
        and creates a properly configured WarningSuppressionManager.

        Args:
            config: Config object with suppression settings.
            project_root: Optional project root for resolving relative paths.

        Returns:
            Configured WarningSuppressionManager instance.
        """
        # Extract suppress_patterns from config
        suppress_patterns = getattr(config, "suppress_warnings", [])

        # Build global pattern suppressions from config
        global_suppressions: Dict[str, bool] = {}
        if hasattr(config, "suppress_dynamic_dispatch_warnings"):
            global_suppressions["dynamic_dispatch"] = config.suppress_dynamic_dispatch_warnings
        if hasattr(config, "suppress_monkey_patching_warnings"):
            global_suppressions["monkey_patching"] = config.suppress_monkey_patching_warnings
        if hasattr(config, "suppress_exec_eval_warnings"):
            global_suppressions["exec_eval"] = config.suppress_exec_eval_warnings
        if hasattr(config, "suppress_decorator_warnings"):
            global_suppressions["decorator"] = config.suppress_decorator_warnings
        if hasattr(config, "suppress_metaclass_warnings"):
            global_suppressions["metaclass"] = config.suppress_metaclass_warnings

        # Extract file-specific suppressions from config
        file_specific = getattr(config, "file_specific_suppressions", {})

        return cls(
            suppress_patterns=suppress_patterns,
            global_pattern_suppressions=global_suppressions,
            file_specific_suppressions=file_specific,
            project_root=project_root,
        )

    def should_suppress(self, warning: StructuredWarning) -> bool:
        """Determine if a warning should be suppressed.

        Applies suppression rules in precedence order (TDD Section 3.9.4):
        1. File-specific pattern-type suppression (most specific)
        2. Global pattern-type suppression
        3. File-level suppression (exact match)
        4. Directory-level suppression (glob pattern match)

        Note: Test module suppression is handled separately by WarningEmitter.

        Args:
            warning: StructuredWarning to evaluate.

        Returns:
            True if warning should be suppressed, False otherwise.
        """
        filepath = warning.file
        pattern_type = warning.type

        # 1. Check file-specific pattern-type suppression (most specific)
        if self._check_file_specific_suppression(filepath, pattern_type):
            logger.debug(f"Warning suppressed by file-specific rule: {filepath}:{pattern_type}")
            return True

        # 2. Check global pattern-type suppression
        if self._check_global_pattern_suppression(pattern_type):
            logger.debug(f"Warning suppressed by global pattern rule: {pattern_type}")
            return True

        # 3. Check file-level suppression (exact path match)
        if self._check_file_suppression(filepath):
            logger.debug(f"Warning suppressed by file-level rule: {filepath}")
            return True

        # 4. Check directory-level suppression (glob pattern match)
        if self._check_directory_suppression(filepath):
            logger.debug(f"Warning suppressed by directory-level rule: {filepath}")
            return True

        return False

    def _check_file_specific_suppression(self, filepath: str, pattern_type: str) -> bool:
        """Check if file has specific suppression for this pattern type.

        Args:
            filepath: File path to check.
            pattern_type: Pattern type to check.

        Returns:
            True if suppressed by file-specific rule.
        """
        # Try exact match first
        if (
            filepath in self.file_specific_suppressions
            and pattern_type in self.file_specific_suppressions[filepath]
        ):
            return True

        # Try relative path match
        try:
            relative_path = self._get_relative_path(filepath)
            if (
                relative_path in self.file_specific_suppressions
                and pattern_type in self.file_specific_suppressions[relative_path]
            ):
                return True
        except ValueError:
            pass  # Path not under project root

        return False

    def _check_global_pattern_suppression(self, pattern_type: str) -> bool:
        """Check if pattern type is globally suppressed.

        Args:
            pattern_type: Pattern type to check.

        Returns:
            True if suppressed by global rule.
        """
        return self.global_pattern_suppressions.get(pattern_type, False)

    def _check_file_suppression(self, filepath: str) -> bool:
        """Check if file is suppressed by exact path match.

        Args:
            filepath: File path to check.

        Returns:
            True if suppressed by file-level rule.
        """
        relative_path = self._get_relative_path(filepath)

        for pattern in self.suppress_patterns:
            # Skip glob patterns (handled by directory suppression)
            if "*" in pattern or "?" in pattern or "[" in pattern:
                continue

            # Exact path match
            if pattern in (filepath, relative_path):
                return True

        return False

    def _check_directory_suppression(self, filepath: str) -> bool:
        """Check if file is suppressed by glob pattern match.

        Supports gitignore-style patterns including:
        - * for any characters within a path segment
        - ** for any number of path segments
        - ? for single character
        - [...] for character classes

        Args:
            filepath: File path to check.

        Returns:
            True if suppressed by directory-level rule.
        """
        relative_path = self._get_relative_path(filepath)

        for pattern in self.suppress_patterns:
            # Only process glob patterns
            if not ("*" in pattern or "?" in pattern or "[" in pattern):
                continue

            # Use Path.match for ** support
            if self._glob_match(relative_path, pattern):
                return True

        return False

    def _glob_match(self, path: str, pattern: str) -> bool:
        """Match a path against a glob pattern with ** support.

        Supports gitignore-style ** pattern for recursive directory matching.

        Args:
            path: Path to match (relative, using forward slashes).
            pattern: Glob pattern to match against.

        Returns:
            True if path matches pattern.
        """
        # Normalize paths to forward slashes
        path = path.replace("\\", "/")
        pattern = pattern.replace("\\", "/")

        # For patterns with **, use custom recursive matcher
        if "**" in pattern:
            return self._match_recursive_glob(path, pattern)

        # For simple patterns, use fnmatch
        return fnmatch.fnmatch(path, pattern)

    def _match_recursive_glob(self, path: str, pattern: str) -> bool:
        """Match a path against a pattern containing ** (recursive glob).

        Args:
            path: Path to match (relative).
            pattern: Glob pattern with ** for recursive matching.

        Returns:
            True if path matches pattern.
        """
        path_parts = path.split("/")
        pattern_parts = pattern.split("/")
        return self._match_parts(path_parts, pattern_parts, 0, 0)

    def _match_parts(
        self,
        path_parts: List[str],
        pattern_parts: List[str],
        pi: int,
        pp: int,
    ) -> bool:
        """Recursively match path parts against pattern parts.

        Args:
            path_parts: List of path components.
            pattern_parts: List of pattern components.
            pi: Current index in path_parts.
            pp: Current index in pattern_parts.

        Returns:
            True if remaining path matches remaining pattern.
        """
        while pi < len(path_parts) and pp < len(pattern_parts):
            if pattern_parts[pp] == "**":
                # ** can match zero or more path segments
                # Try matching with 0, 1, 2, ... path segments
                for skip in range(len(path_parts) - pi + 1):
                    if self._match_parts(path_parts, pattern_parts, pi + skip, pp + 1):
                        return True
                return False
            elif fnmatch.fnmatch(path_parts[pi], pattern_parts[pp]):
                pi += 1
                pp += 1
            else:
                return False

        # Handle trailing **
        while pp < len(pattern_parts) and pattern_parts[pp] == "**":
            pp += 1

        return pi == len(path_parts) and pp == len(pattern_parts)

    def _get_relative_path(self, filepath: str) -> str:
        """Get relative path from project root.

        Normalizes paths to resolve traversal sequences (.. and .) before
        computing the relative path. This ensures consistent matching and
        prevents directory traversal from bypassing suppression rules.

        Args:
            filepath: Absolute or relative file path.

        Returns:
            Path relative to project root, or original filepath if
            outside project root or on error.
        """
        try:
            path = Path(filepath)
            if path.is_absolute():
                # Normalize path to resolve .. and . components
                normalized = path.resolve()
                project_root_resolved = self.project_root.resolve()
                return str(normalized.relative_to(project_root_resolved))
            return filepath
        except ValueError:
            # Path is not under project root after normalization
            return filepath

    def filter_warnings(self, warnings: List[StructuredWarning]) -> List[StructuredWarning]:
        """Filter a list of warnings, removing suppressed ones.

        Args:
            warnings: List of warnings to filter.

        Returns:
            List of warnings that are not suppressed.
        """
        return [w for w in warnings if not self.should_suppress(w)]

    def get_suppression_reason(self, warning: StructuredWarning) -> Optional[str]:
        """Get human-readable reason for suppression.

        Args:
            warning: StructuredWarning to check.

        Returns:
            Reason string if suppressed, None otherwise.
        """
        filepath = warning.file
        pattern_type = warning.type

        # Check each rule in precedence order
        if self._check_file_specific_suppression(filepath, pattern_type):
            return f"File-specific suppression for {pattern_type}"

        if self._check_global_pattern_suppression(pattern_type):
            return f"Global suppression for {pattern_type}"

        if self._check_file_suppression(filepath):
            return f"File-level suppression for {filepath}"

        if self._check_directory_suppression(filepath):
            return "Directory-level suppression matching pattern"

        return None
