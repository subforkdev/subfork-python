"""Synchronous, explicitly closed HTTP client. No automatic write retries."""

from __future__ import annotations

import math
import os
import re
import tempfile
from pathlib import Path
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
from .resources import Artifacts, Assets, Executions, Graphs, Nodes


def _error_message(response: httpx.Response) -> str:
    """Translate recognized server errors into fixed, credential-safe guidance."""
    message = "Subfork API returned HTTP %s." % response.status_code
    if response.status_code != 409:
        return message
    try:
        payload = response.json()
    except (ValueError, httpx.ResponseNotRead):
        return message
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and re.fullmatch(
        r"Graph secret '[^\r\n]*' could not be decrypted\. The server encryption "
        r"key may have changed; re-enter this secret in Graph Settings\.",
        detail,
    ):
        return (
            message + " A stored graph secret could not be decrypted. "
            "The server encryption key may have changed. "
            "Re-enter and save the affected secret in Graph Settings > Secrets, then retry."
        )
    return message


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
        self.artifacts = Artifacts(self)
        self.assets = Assets(self)
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
        self._check_response(response)
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError:
            raise InvalidResponseError("API returned invalid JSON.") from None

    @staticmethod
    def _check_response(response: httpx.Response) -> None:
        """Raise a credential-safe API exception for an unsuccessful response."""
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
                _error_message(response),
                status_code=response.status_code,
                retry_after=response.headers.get("retry-after"),
            )

    def _download(self, path: str, destination: Path, *, overwrite: bool, max_bytes: int) -> Path:
        """Stream an artifact, stripping credentials on a storage redirect."""
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive.")
        if destination.exists() and not overwrite:
            raise FileExistsError("Output file already exists; set overwrite=True.")
        temporary = None
        response = None
        try:
            request = self._client.build_request("GET", path.lstrip("/"))
            response = self._client.send(request, stream=True)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise InvalidResponseError("Artifact redirect has no location.")
                try:
                    target = response.url.join(location)
                except httpx.InvalidURL:
                    raise InvalidResponseError(
                        "Artifact redirect contains an invalid URL."
                    ) from None
                if target.scheme != "https" or target.userinfo or target.fragment:
                    raise InvalidResponseError(
                        "Artifact redirect must use HTTPS without credentials."
                    )
                response.close()
                # A fresh Request does not inherit the API client's headers or cookies.
                response = self._client.send(
                    httpx.Request("GET", target), stream=True, auth=None, follow_redirects=False
                )
            self._check_response(response)
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix=".subfork-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                size = 0
                for chunk in response.iter_bytes(chunk_size=65536):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Artifact exceeds max_bytes; partial download discarded.")
                    stream.write(chunk)
            if overwrite:
                os.replace(temporary, destination)
            else:
                # Exclusive publication also protects against another writer racing us.
                os.link(temporary, destination)
            return destination
        except httpx.TransportError:
            raise TransportError("Artifact download could not be completed.") from None
        finally:
            if response is not None:
                response.close()
            if temporary is not None:
                temporary.unlink(missing_ok=True)

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
