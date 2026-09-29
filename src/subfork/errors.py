"""Public client errors; credentials and raw responses are never attached."""

from typing import Optional


class SubforkError(Exception):
    """Base class for client errors."""


class TransportError(SubforkError):
    """The request could not be completed; a write's outcome may be unknown."""


class APIError(SubforkError):
    """Represent an HTTP failure without retaining a raw request or response."""

    def __init__(
        self, message: str, *, status_code: int, retry_after: Optional[str] = None
    ) -> None:
        """Store a safe message, HTTP status, and optional Retry-After header."""
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class AuthenticationError(APIError):
    """Report HTTP 401 for missing, expired, or invalid credentials."""

    pass


class PermissionDeniedError(APIError):
    """Report HTTP 403 when the credential cannot perform an operation."""

    pass


class NotFoundError(APIError):
    """Report HTTP 404 for a missing or inaccessible resource."""

    pass


class ValidationError(APIError):
    """Report HTTP 422 when server request validation fails."""

    pass


class RateLimitError(APIError):
    """Report HTTP 429, with an optional Retry-After header."""

    pass


class InvalidResponseError(SubforkError):
    """Report a successful HTTP response containing invalid JSON."""

    pass


class ExecutionTimeout(SubforkError):
    """Polling expired. The remote execution was not cancelled."""

    def __init__(self, execution_id: str) -> None:
        """Identify the execution whose polling deadline expired."""
        super().__init__("Execution polling timed out; the remote execution may still be running.")
        self.execution_id = execution_id
