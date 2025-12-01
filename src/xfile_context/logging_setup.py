# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Structured logging setup for Cross-File Context Links."""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add any extra fields
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


def setup_logging(
    log_dir: Optional[Path] = None,
    log_level: int = logging.INFO,
    console_output: bool = True,
) -> None:
    """Set up structured logging for the application.

    Args:
        log_dir: Directory for log files. If None, uses .cross_file_context_logs/
        log_level: Logging level (default: INFO)
        console_output: Whether to also output to console (default: True)
    """
    if log_dir is None:
        log_dir = Path.cwd() / ".cross_file_context_logs"

    # Create log directory if it doesn't exist
    log_dir.mkdir(exist_ok=True)

    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove any existing handlers
    root_logger.handlers.clear()

    # File handler with structured JSON logging
    log_file = log_dir / f"xfile_context_{datetime.utcnow().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(file_handler)

    # Console handler with human-readable format (if enabled)
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # Log startup message
    logging.info(f"Logging initialized. Log directory: {log_dir}")


def get_metrics_logger(log_dir: Optional[Path] = None) -> logging.Logger:
    """Get logger for session metrics.

    Args:
        log_dir: Directory for log files. If None, uses .cross_file_context_logs/

    Returns:
        Logger configured for metrics output
    """
    if log_dir is None:
        log_dir = Path.cwd() / ".cross_file_context_logs"

    log_dir.mkdir(exist_ok=True)

    # Create metrics-specific logger
    metrics_logger = logging.getLogger("xfile_context.metrics")
    metrics_logger.setLevel(logging.INFO)
    metrics_logger.propagate = False  # Don't propagate to root logger

    # Remove any existing handlers
    metrics_logger.handlers.clear()

    # Metrics file handler (JSONL format)
    metrics_file = log_dir / "session_metrics.jsonl"
    metrics_handler = logging.FileHandler(metrics_file, encoding="utf-8")
    metrics_handler.setLevel(logging.INFO)
    metrics_handler.setFormatter(StructuredFormatter())
    metrics_logger.addHandler(metrics_handler)

    return metrics_logger
