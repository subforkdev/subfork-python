"""Small resource wrappers over the existing versioned HTTP API."""
from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from .errors import ExecutionTimeout

if TYPE_CHECKING:
    from .client import Subfork


def segment(value: str) -> str:
    if not value or value in {'.', '..'}:
        raise ValueError('Resource identifiers must be non-empty and cannot be dot segments.')
    return quote(value, safe='')


class Resource:
    def __init__(self, client: Subfork):
        self._client = client


class Nodes(Resource):
    def list(self, *, include_all_versions: bool = False) -> list[dict[str, Any]]:
        return self._client._request('GET', '/nodes', params={'include_all_versions': include_all_versions})

    def get(self, node_id: str) -> dict[str, Any]:
        return self._client._request('GET', '/nodes/' + segment(node_id))


class Graphs(Resource):
    def list(self) -> list[dict[str, Any]]:
        return self._client._request('GET', '/graphs')

    def get(self, graph_id: str) -> dict[str, Any]:
        return self._client._request('GET', '/graphs/' + segment(graph_id))

    def validate(self, definition: dict[str, Any], *, name: str | None = None) -> dict[str, Any]:
        return self._client._request('POST', '/graphs/validate', json={
            'name': name if name is not None else definition.get('name', 'Untitled Graph'), 'definition': definition})

    def create(self, *, name: str, definition: dict[str, Any], description: str = '', tags: list[str] | None = None) -> dict[str, Any]:
        return self._client._request('POST', '/graphs', json={
            'name': name, 'description': description, 'definition': definition, 'tags': tags or []})

    def update(self, graph_id: str, *, name: str, definition: dict[str, Any], description: str = '') -> dict[str, Any]:
        return self._client._request('PUT', '/graphs/' + segment(graph_id), json={
            'name': name, 'description': description, 'definition': definition})

    def published(self) -> list[dict[str, Any]]:
        return self._client._request('GET', '/graphs/published')

    def versions(self, graph_id: str) -> list[dict[str, Any]]:
        return self._client._request('GET', '/graphs/' + segment(graph_id) + '/versions')

    def published_version(self, graph_id: str, version: str) -> dict[str, Any]:
        return self._client._request('GET', '/graphs/published/' + segment(graph_id) + '/versions/' + segment(version))

    def interface(self, graph_id: str) -> dict[str, Any]:
        return self._client._request('GET', '/graphs/' + segment(graph_id) + '/interface-preview')

    def publish(self, graph_id: str, *, version: str, interface: dict[str, Any] | None = None, comment: str = '') -> dict[str, Any]:
        payload: dict[str, Any] = {'version': version, 'comment': comment}
        if interface is not None:
            payload['interface'] = interface
        return self._client._request('POST', '/graphs/' + segment(graph_id) + '/versions', json=payload)

    def execute(self, graph_id: str, *, version: str = 'draft', inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._client._request('POST', '/graphs/' + segment(graph_id) + '/execute',
                                     params={'version': version}, json={'inputs': inputs or {}})


class Executions(Resource):
    def get(self, execution_id: str) -> dict[str, Any]:
        return self._client._request('GET', '/executions/' + segment(execution_id))

    def cancel(self, execution_id: str) -> dict[str, Any]:
        return self._client._request('POST', '/executions/' + segment(execution_id) + '/cancel')

    def wait(self, execution_id: str, *, timeout: float = 120, poll_interval: float = 2) -> dict[str, Any]:
        if not math.isfinite(timeout) or timeout <= 0 or not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError('timeout and poll_interval must be positive finite numbers.')
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ExecutionTimeout(execution_id)
            result = self._client._request('GET', '/executions/' + segment(execution_id),
                                          timeout=min(self._client.timeout, remaining))
            if result['status'] in {'completed', 'failed', 'canceled', 'cancelled', 'outcome_unknown'}:
                return result
            time.sleep(min(poll_interval, max(0, deadline - time.monotonic())))
