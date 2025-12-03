# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""API middleware implementations."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from tests.functional.test_codebase.api.endpoints import APIResponse


@dataclass
class Request:
    """Represents an API request."""

    method: str
    path: str
    headers: dict[str, str]
    body: Any = None
    user_id: str | None = None


class Middleware(ABC):
    """Abstract base class for middleware."""

    @abstractmethod
    def process(
        self, request: Request, next_handler: Callable[[Request], APIResponse]
    ) -> APIResponse:
        """Process a request through the middleware.

        Args:
            request: The incoming request.
            next_handler: The next handler in the chain.

        Returns:
            An APIResponse.
        """
        pass


class AuthMiddleware(Middleware):
    """Middleware for authentication."""

    def __init__(self, auth_header: str = "Authorization") -> None:
        """Initialize the auth middleware.

        Args:
            auth_header: The header name for auth tokens.
        """
        self.auth_header = auth_header
        self.logger = logging.getLogger(self.__class__.__name__)
        # In a real app, this would validate tokens properly
        self._valid_tokens: set[str] = set()

    def add_token(self, token: str) -> None:
        """Add a valid token.

        Args:
            token: The token to add.
        """
        self._valid_tokens.add(token)

    def process(
        self, request: Request, next_handler: Callable[[Request], APIResponse]
    ) -> APIResponse:
        """Process authentication.

        Args:
            request: The incoming request.
            next_handler: The next handler in the chain.

        Returns:
            An APIResponse.
        """
        token = request.headers.get(self.auth_header)

        if not token:
            self.logger.warning(f"No auth token for request to {request.path}")
            return APIResponse(success=False, error="Authentication required", status_code=401)

        if token not in self._valid_tokens:
            self.logger.warning(f"Invalid auth token for request to {request.path}")
            return APIResponse(success=False, error="Invalid token", status_code=401)

        self.logger.debug(f"Authenticated request to {request.path}")
        return next_handler(request)


class LoggingMiddleware(Middleware):
    """Middleware for request/response logging."""

    def __init__(self) -> None:
        """Initialize the logging middleware."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.request_log: list[dict[str, Any]] = []

    def process(
        self, request: Request, next_handler: Callable[[Request], APIResponse]
    ) -> APIResponse:
        """Log requests and responses.

        Args:
            request: The incoming request.
            next_handler: The next handler in the chain.

        Returns:
            An APIResponse.
        """
        start_time = time.time()

        self.logger.info(f"Request: {request.method} {request.path}")

        response = next_handler(request)

        elapsed_ms = (time.time() - start_time) * 1000

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "method": request.method,
            "path": request.path,
            "status_code": response.status_code,
            "elapsed_ms": round(elapsed_ms, 2),
            "success": response.success,
        }
        self.request_log.append(log_entry)

        self.logger.info(f"Response: {response.status_code} ({elapsed_ms:.2f}ms)")

        return response

    def get_logs(self, count: int | None = None) -> list[dict[str, Any]]:
        """Get recent request logs.

        Args:
            count: Number of logs to return. None for all.

        Returns:
            A list of log entries.
        """
        if count is None:
            return self.request_log.copy()
        return self.request_log[-count:]

    def clear_logs(self) -> None:
        """Clear all logged requests."""
        self.request_log.clear()


class RateLimitMiddleware(Middleware):
    """Middleware for rate limiting."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60) -> None:
        """Initialize the rate limit middleware.

        Args:
            max_requests: Maximum requests per window.
            window_seconds: Time window in seconds.
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.logger = logging.getLogger(self.__class__.__name__)
        self._request_times: dict[str, list[float]] = {}

    def process(
        self, request: Request, next_handler: Callable[[Request], APIResponse]
    ) -> APIResponse:
        """Apply rate limiting.

        Args:
            request: The incoming request.
            next_handler: The next handler in the chain.

        Returns:
            An APIResponse.
        """
        client_id = request.user_id or request.headers.get("X-Client-ID", "anonymous")
        now = time.time()

        # Clean up old entries
        if client_id in self._request_times:
            self._request_times[client_id] = [
                t for t in self._request_times[client_id] if now - t < self.window_seconds
            ]
        else:
            self._request_times[client_id] = []

        # Check rate limit
        if len(self._request_times[client_id]) >= self.max_requests:
            self.logger.warning(f"Rate limit exceeded for {client_id}")
            return APIResponse(success=False, error="Rate limit exceeded", status_code=429)

        # Record request time
        self._request_times[client_id].append(now)

        return next_handler(request)
