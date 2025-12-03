# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-17: Massive Files

This module demonstrates handling of very large files.
Files exceeding 10,000 lines should be skipped with a warning.

Expected behavior:
- Skip indexing files >10,000 lines
- Log warning about massive file
- Treat file as opaque (no relationship tracking)

NOTE: This file itself is not massive. It represents code that would
REFERENCE massive files. The actual massive file would be generated
or exist separately for testing.
"""

from typing import Any, Iterator

from tests.functional.test_codebase.core.models.base import BaseModel


class MassiveFileHandler:
    """Handler for massive files that exceed analysis limits.

    When the analyzer encounters a file with >10,000 lines,
    it should skip indexing and treat it as opaque.
    """

    MAX_LINES = 10000

    def __init__(self) -> None:
        self.skipped_files: list[str] = []
        self.processed_files: list[str] = []

    def should_process(self, file_path: str, line_count: int) -> bool:
        """Check if a file should be processed.

        Args:
            file_path: Path to the file.
            line_count: Number of lines in the file.

        Returns:
            True if file should be processed, False if too large.
        """
        if line_count > self.MAX_LINES:
            self.skipped_files.append(file_path)
            return False
        self.processed_files.append(file_path)
        return True

    def get_stats(self) -> dict[str, Any]:
        """Get processing statistics."""
        return {
            "processed": len(self.processed_files),
            "skipped": len(self.skipped_files),
            "skipped_files": self.skipped_files,
        }


class GeneratedCodeHandler:
    """Handler for generated code files which are often massive.

    Generated files (ORM models, protobuf, etc.) often exceed
    10,000 lines and should be treated specially.
    """

    GENERATED_PATTERNS = [
        "_generated.py",
        "_pb2.py",
        "_pb2_grpc.py",
        "migrations/",
        "generated/",
    ]

    def is_generated(self, file_path: str) -> bool:
        """Check if a file appears to be generated."""
        return any(pattern in file_path for pattern in self.GENERATED_PATTERNS)

    def handle_generated_file(self, file_path: str) -> dict[str, Any]:
        """Handle a generated file.

        Generated files are typically not analyzed for relationships
        because they're auto-generated and can be massive.
        """
        return {
            "file": file_path,
            "type": "generated",
            "analysis": "skipped",
            "reason": "Generated files are treated as opaque",
        }


def count_lines(content: str) -> int:
    """Count lines in file content."""
    return content.count("\n") + 1


def stream_large_file(file_path: str, chunk_size: int = 1000) -> Iterator[list[str]]:
    """Stream a large file in chunks.

    This is a pattern for handling massive files without
    loading them entirely into memory.

    Args:
        file_path: Path to the file.
        chunk_size: Number of lines per chunk.

    Yields:
        Chunks of lines.
    """
    chunk: list[str] = []
    # Simulated - in real code this would read from disk
    for i in range(chunk_size * 10):  # Simulate 10 chunks
        chunk.append(f"Line {i}: content")
        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


class LargeFileWarning:
    """Warning information for large files."""

    def __init__(self, file_path: str, line_count: int) -> None:
        self.file_path = file_path
        self.line_count = line_count
        self.message = (
            f"File {file_path} has {line_count} lines "
            f"(exceeds {MassiveFileHandler.MAX_LINES} limit). "
            "Treating as opaque - no relationship tracking."
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert warning to dictionary."""
        return {
            "type": "large_file_warning",
            "file": self.file_path,
            "lines": self.line_count,
            "limit": MassiveFileHandler.MAX_LINES,
            "message": self.message,
        }


# Example of referencing BaseModel (a normal-sized file)
# to show contrast with massive files
def create_model(name: str) -> type:
    """Create a model class inheriting from BaseModel.

    This uses the normal-sized BaseModel file, not a massive file.
    """

    class DynamicModel(BaseModel):
        model_name: str = name

    return DynamicModel
