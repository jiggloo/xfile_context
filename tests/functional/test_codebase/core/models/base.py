# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Base model class for all data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass
class BaseModel:
    """Base class for all data models with common functionality."""

    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary representation."""
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def update(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now()

    @classmethod
    def validate_id(cls, id_value: str) -> bool:
        """Validate that an ID is in the correct format."""
        if not id_value or not isinstance(id_value, str):
            return False
        # UUID format: 8-4-4-4-12
        parts = id_value.split("-")
        return len(parts) == 5 and all(len(p) > 0 for p in parts)
