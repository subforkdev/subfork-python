"""Synchronous, explicitly closed HTTP client. No automatic write retries."""

from __future__ import annotations

import math
import os
from types import TracebackType
from typing import Any, Optional, Type

import httpx

from .errors import (
    APIError,
    AuthenticationError,
    InvalidResponseError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    TransportError,
    ValidationError,
)
from .resources import Executions, Graphs, Nodes


class Subfork:
    """Manage authenticated HTTP requests and graph resources.

    The client owns its connection pool. Use a context manager or close() to
    release it. Writes are never automatically retried.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = "https://subfork.com",
        timeout: float = 30,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        """Create an authenticated client for the Subfork API.

        Args:
            api_key: Bearer secret, or None to read SUBFORK_API_KEY.
            base_url: API origin, defaulting to https://subfork.com, without
                an API path, query, or credentials.
            timeout: Positive per-I/O-phase HTTP timeout in seconds.
            transport: Optional HTTPX transport, primarily for testing.

        Raises:
            ValueError: Credentials, origin, or timeout are invalid.
        """
        key = os.environ.get("SUBFORK_API_KEY") if api_key is None else api_key
        if not key or any(char.isspace() for char in key):
            raise ValueError(
                "Provide an API key or set SUBFORK_API_KEY; keys cannot contain whitespace."
            )
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive finite number.")
        origin = httpx.URL(base_url)
        if (
            not origin.host
            or origin.userinfo
            or origin.query
            or origin.fragment
            or origin.path not in {"", "/"}
        ):
            raise ValueError(
                "base_url must be an origin without credentials, path, query or fragment."
            )
        if origin.scheme != "https" and not (
            origin.scheme == "http"
            and (
                origin.host in {"localhost", "127.0.0.1", "::1"}
                or origin.host.endswith(".localhost")
            )
        ):
            raise ValueError("Use HTTPS; HTTP is allowed only for localhost.")
        self.timeout = timeout
        self._client = httpx.Client(
            base_url=str(origin).rstrip("/") + "/api/v1/",
            timeout=timeout,
            headers={"Authorization": "Bearer " + key, "Accept": "application/json"},
            follow_redirects=False,
            transport=transport,
        )
        self.nodes = Nodes(self)
        self.graphs = Graphs(self)
        self.executions = Executions(self)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Send one request and decode JSON, returning None for HTTP 204.

        Raise APIError subclasses for HTTP failures, TransportError for network
        failures, and InvalidResponseError for invalid JSON. Error messages
        never include response bodies or credentials.
        """
        try:
            response = self._client.request(method, path.lstrip("/"), **kwargs)
        except httpx.TransportError:
            raise TransportError(
                "API request could not be completed; inspect remote state before retrying a write."
            ) from None
        if not response.is_success:
            errors = {
                401: AuthenticationError,
                403: PermissionDeniedError,
                404: NotFoundError,
                422: ValidationError,
                429: RateLimitError,
            }
            # Fixed messages avoid reflecting secrets from an untrusted response.
            raise errors.get(response.status_code, APIError)(
                "Subfork API returned HTTP %s." % response.status_code,
                status_code=response.status_code,
                retry_after=response.headers.get("retry-after"),
            )
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError:
            raise InvalidResponseError("API returned invalid JSON.") from None

    def close(self) -> None:
        """Release the HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> Subfork:
        """Return this client for use in a with statement."""
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Close the client without suppressing exceptions."""
        self.close()
