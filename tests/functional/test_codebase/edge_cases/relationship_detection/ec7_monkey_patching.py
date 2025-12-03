# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-7: Monkey Patching (Unhandled in v0.1.0)

This module demonstrates monkey patching patterns.
These runtime modifications cannot be tracked statically.

Expected behavior:
- Analyzer should emit warning for monkey patching in source modules
- Analyzer should NOT emit warnings in test modules (for mocking)
- Relationship graph tracks original definitions only
"""

from typing import Callable

# Import modules that will be monkey patched
from tests.functional.test_codebase.core.utils import validation

# Store original function for restoration
_original_validate_email = validation.validate_email


def custom_email_validator(email: str) -> bool:
    """Custom email validator that replaces the original.

    This replaces validation.validate_email at runtime.
    The analyzer cannot track that code using validate_email
    will now call this function instead.
    """
    # More lenient validation for testing
    return "@" in email


def enable_lenient_validation() -> None:
    """Enable lenient email validation by monkey patching.

    WARNING: This modifies the validation module at runtime.
    The analyzer will emit a warning about this pattern.
    """
    # Monkey patch - runtime replacement of module attribute
    validation.validate_email = custom_email_validator


def restore_strict_validation() -> None:
    """Restore the original strict email validation."""
    validation.validate_email = _original_validate_email


class ModuleModifier:
    """Class that modifies module attributes dynamically."""

    def __init__(self, module) -> None:
        self.module = module
        self.patches: dict[str, Callable] = {}
        self.originals: dict[str, Callable] = {}

    def patch(self, attr_name: str, replacement: Callable) -> None:
        """Patch a module attribute with a replacement.

        This is monkey patching - replacing module.attr at runtime.
        """
        self.originals[attr_name] = getattr(self.module, attr_name)
        self.patches[attr_name] = replacement
        # Monkey patch
        setattr(self.module, attr_name, replacement)

    def unpatch(self, attr_name: str) -> None:
        """Restore the original attribute."""
        if attr_name in self.originals:
            setattr(self.module, attr_name, self.originals[attr_name])
            del self.originals[attr_name]
            del self.patches[attr_name]

    def unpatch_all(self) -> None:
        """Restore all patched attributes."""
        for attr_name in list(self.originals.keys()):
            self.unpatch(attr_name)


# Example of class method monkey patching
class OriginalClass:
    """A class that will be monkey patched."""

    def original_method(self) -> str:
        """The original method."""
        return "original"


def patched_method(self) -> str:
    """A replacement method."""
    return "patched"


def patch_class_method() -> None:
    """Patch a class method at runtime."""
    # Monkey patch class method
    OriginalClass.original_method = patched_method  # type: ignore[method-assign]
