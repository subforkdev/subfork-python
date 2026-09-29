"""Subfork's Python API client. BYO worker support is a separate distribution."""

from .client import Subfork
from .errors import (
    APIError,
    AuthenticationError,
    ExecutionTimeout,
    InvalidResponseError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    SubforkError,
    TransportError,
    ValidationError,
)

__version__ = "2.0.0"
__all__ = [
    "Subfork",
    "SubforkError",
    "APIError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "ValidationError",
    "RateLimitError",
    "TransportError",
    "InvalidResponseError",
    "ExecutionTimeout",
]
