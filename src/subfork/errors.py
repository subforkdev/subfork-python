"""Public client errors; credentials and raw responses are never attached."""
from typing import Optional


class SubforkError(Exception):
    """Base class for client errors."""


class TransportError(SubforkError):
    """The request could not be completed; a write's outcome may be unknown."""


class APIError(SubforkError):
    def __init__(self, message: str, *, status_code: int, retry_after: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class AuthenticationError(APIError):
    pass


class PermissionDeniedError(APIError):
    pass


class NotFoundError(APIError):
    pass


class ValidationError(APIError):
    pass


class RateLimitError(APIError):
    pass


class InvalidResponseError(SubforkError):
    pass


class ExecutionTimeout(SubforkError):
    """Polling expired. The remote execution was not cancelled."""

    def __init__(self, execution_id: str):
        super().__init__("Execution polling timed out; the remote execution may still be running.")
        self.execution_id = execution_id
