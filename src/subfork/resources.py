"""Small resource wrappers over the existing versioned HTTP API."""

from __future__ import annotations

import math
import mimetypes
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union
from urllib.parse import quote

from .errors import ExecutionTimeout

if TYPE_CHECKING:
    from .client import Subfork


def segment(value: str) -> str:
    """Encode an identifier as a path segment, rejecting empty or dot segments."""
    if not value or value in {".", ".."}:
        raise ValueError("Resource identifiers must be non-empty and cannot be dot segments.")
    return quote(value, safe="")


class Resource:
    """Share a client connection with a resource-specific wrapper."""

    def __init__(self, client: Subfork) -> None:
        """Bind this wrapper to its owning client."""
        self._client = client


class Nodes(Resource):
    """Discover available node implementations and manifests."""

    def list(self, *, include_all_versions: bool = False) -> List[Dict[str, Any]]:
        """Return node manifests, optionally including older published versions."""
        return self._client._request(
            "GET", "/nodes", params={"include_all_versions": include_all_versions}
        )

    def get(self, node_id: str) -> Dict[str, Any]:
        """Return the current public manifest for a node ID."""
        return self._client._request("GET", "/nodes/" + segment(node_id))


class Graphs(Resource):
    """Author drafts and discover or publish reusable graph versions."""

    def list(self) -> List[Dict[str, Any]]:
        """Return the account graph listing."""
        return self._client._request("GET", "/graphs")

    def get(self, graph_id: str) -> Dict[str, Any]:
        """Return an accessible graph by ID."""
        return self._client._request("GET", "/graphs/" + segment(graph_id))

    def validate(self, definition: Dict[str, Any], *, name: Optional[str] = None) -> Dict[str, Any]:
        """Validate a candidate without saving it or executing nodes.

        An omitted name defaults to the definition name or Untitled Graph.
        Validation does not guarantee that runtime execution will succeed.
        """
        return self._client._request(
            "POST",
            "/graphs/validate",
            json={
                "name": name if name is not None else definition.get("name", "Untitled Graph"),
                "definition": definition,
            },
        )

    def create(
        self,
        *,
        name: str,
        definition: Dict[str, Any],
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a public draft and return its server representation.

        Requires graphs:write. Inspect remote state before retrying a request
        with an uncertain outcome to avoid creating duplicate graphs.
        """
        return self._client._request(
            "POST",
            "/graphs",
            json={
                "name": name,
                "description": description,
                "definition": definition,
                "tags": tags or [],
            },
        )

    def update(
        self, graph_id: str, *, name: str, definition: Dict[str, Any], description: str = ""
    ) -> Dict[str, Any]:
        """Replace the submitted draft fields of an owned graph.

        Requires graphs:write. Pass description to preserve its value; the
        default empty string clears it.
        """
        return self._client._request(
            "PUT",
            "/graphs/" + segment(graph_id),
            json={"name": name, "description": description, "definition": definition},
        )

    def published(self) -> List[Dict[str, Any]]:
        """Return the published reusable graph catalog."""
        return self._client._request("GET", "/graphs/published")

    def versions(self, graph_id: str) -> List[Dict[str, Any]]:
        """Return stored versions of an owned graph."""
        return self._client._request("GET", "/graphs/" + segment(graph_id) + "/versions")

    def published_version(self, graph_id: str, version: str) -> Dict[str, Any]:
        """Return a published definition, interface, and composite node manifest."""
        return self._client._request(
            "GET", "/graphs/published/" + segment(graph_id) + "/versions/" + segment(version)
        )

    def interface(self, graph_id: str) -> Dict[str, Any]:
        """Preview the server-inferred interface of an owned graph draft."""
        return self._client._request("GET", "/graphs/" + segment(graph_id) + "/interface-preview")

    def publish(
        self,
        graph_id: str,
        *,
        version: str,
        interface: Optional[Dict[str, Any]] = None,
        comment: str = "",
    ) -> Dict[str, Any]:
        """Publish an immutable version of an owned graph.

        Requires graphs:publish. The server infers the interface if omitted.
        This creates public content and is not automatically retried.
        """
        payload: Dict[str, Any] = {"version": version, "comment": comment}
        if interface is not None:
            payload["interface"] = interface
        return self._client._request(
            "POST", "/graphs/" + segment(graph_id) + "/versions", json=payload
        )

    def execute(
        self, graph_id: str, *, version: str = "draft", inputs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Submit an owned graph and return its initial execution state.

        Requires graphs:run and consumes account quota. Select draft, published,
        or an explicit version, and pass graph inputs as a dictionary. This
        method does not wait for completion or retry failed submissions.
        """
        return self._client._request(
            "POST",
            "/graphs/" + segment(graph_id) + "/execute",
            params={"version": version},
            json={"inputs": inputs or {}},
        )


class Executions(Resource):
    """Inspect, cancel, and poll account-owned executions."""

    def get(self, execution_id: str) -> Dict[str, Any]:
        """Return an owned execution snapshot, including status and outputs."""
        return self._client._request("GET", "/executions/" + segment(execution_id))

    def cancel(self, execution_id: str) -> Dict[str, Any]:
        """Request cancellation and return the execution snapshot."""
        return self._client._request("POST", "/executions/" + segment(execution_id) + "/cancel")

    def wait(
        self,
        execution_id: str,
        *,
        timeout: float = 120,
        poll_interval: float = 2,
        on_update: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Poll until a terminal status or the polling deadline.

        Args:
            execution_id: Identifier of the execution to observe.
            timeout: Positive deadline in seconds. Remaining time caps HTTP
                timeouts, which apply per I/O phase, not to the entire request.
            poll_interval: Positive delay in seconds between status requests.
            on_update: Optional synchronous callback for each retrieved snapshot.
                Callback exceptions propagate to the caller without canceling the run.

        Returns:
            The terminal snapshot, including failed or canceled executions.

        Raises:
            ValueError: A timing argument is nonpositive or nonfinite.
            ExecutionTimeout: Polling expired; the remote run is not canceled.
            SubforkError: A status request failed; it is not retried.
        """
        if (
            not math.isfinite(timeout)
            or timeout <= 0
            or not math.isfinite(poll_interval)
            or poll_interval <= 0
        ):
            raise ValueError("timeout and poll_interval must be positive finite numbers.")
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ExecutionTimeout(execution_id)
            result = self._client._request(
                "GET",
                "/executions/" + segment(execution_id),
                timeout=min(self._client.timeout, remaining),
            )
            if on_update is not None:
                on_update(result)
            if result["status"] in {
                "completed",
                "failed",
                "canceled",
                "cancelled",
                "outcome_unknown",
            }:
                return result
            time.sleep(min(poll_interval, max(0, deadline - time.monotonic())))


class Artifacts(Resource):
    """Download artifacts accessible to the API-key account."""

    def download(
        self,
        artifact_id: str,
        destination: Union[str, os.PathLike],
        *,
        overwrite: bool = False,
        max_bytes: int = 250_000_000,
    ) -> Path:
        """Stream bytes to a file and return its path after successful completion.

        The parent directory must exist. Failed downloads leave no partial output
        and preserve an existing destination. Set overwrite explicitly to replace
        it. At most one HTTPS storage redirect is followed, without API credentials.
        The default decoded-byte limit is 250 MB; increase it for larger media.
        Requires graphs:read and access to the unexpired artifact.
        """
        return self._client._download(
            "/artifacts/" + segment(artifact_id),
            Path(destination),
            overwrite=overwrite,
            max_bytes=max_bytes,
        )


class Assets(Resource):
    """Manage input files belonging to an owned graph."""

    def list(self, graph_id: str, *, include_generated: bool = False) -> Dict[str, Any]:
        """Return the server's assets envelope; generated outputs are opt-in."""
        return self._client._request(
            "GET",
            "/graphs/" + segment(graph_id) + "/assets",
            params={"include_generated": include_generated},
        )

    def upload(
        self,
        graph_id: str,
        source: Union[str, os.PathLike],
        *,
        content_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload a local file and return artifact metadata, including artifact_id.

        Requires graphs:write on a server supporting API-key asset uploads.
        Upload quotas, file validation and the uploads feature switch still apply.
        This stores an asset; it does not select it on a node or execute the graph.
        The file is streamed from disk and the operation is never retried.
        """
        path = Path(source)
        media_type = (
            content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        )
        with path.open("rb") as stream:
            return self._client._request(
                "POST",
                "/graphs/" + segment(graph_id) + "/assets/files",
                files={"upload": (path.name, stream, media_type)},
            )
