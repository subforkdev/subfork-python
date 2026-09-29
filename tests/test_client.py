"""Exercise client contracts without network access or real credentials."""

import json
from typing import Type

import httpx
import pytest

from subfork import (
    APIError,
    AuthenticationError,
    ExecutionTimeout,
    PermissionDeniedError,
    RateLimitError,
    Subfork,
    TransportError,
    ValidationError,
)

KEY = "synthetic-test-key"


def test_bearer_auth_base_url_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify bearer auth base url and environment."""
    monkeypatch.setenv("SUBFORK_API_KEY", KEY)
    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        """Handle a mocked HTTP request for this scenario."""
        seen.append(request)
        return httpx.Response(200, json=[])

    with Subfork(
        base_url="http://subfork.localhost", transport=httpx.MockTransport(handle)
    ) as client:
        assert client.nodes.list(include_all_versions=True) == []
    assert str(seen[0].url) == "http://subfork.localhost/api/v1/nodes?include_all_versions=true"
    assert seen[0].headers["authorization"] == "Bearer " + KEY
    assert KEY not in str(seen[0].url)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:pass@example.com",
        "https://example.com/api/v1",
        "https://example.com?key=x",
        "http://localhost.evil.example",
        "https://example.com#fragment",
    ],
)
def test_reject_unsafe_or_ambiguous_origins(url: str) -> None:
    """Verify reject unsafe or ambiguous origins."""
    with pytest.raises(ValueError):
        Subfork(KEY, base_url=url)


def test_credentials_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify credentials required."""
    monkeypatch.delenv("SUBFORK_API_KEY", raising=False)
    with pytest.raises(ValueError):
        Subfork()


@pytest.mark.parametrize(
    "status,error",
    [
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (422, ValidationError),
        (429, RateLimitError),
        (503, APIError),
    ],
)
def test_errors_do_not_echo_response_secrets(status: int, error: Type[APIError]) -> None:
    """Verify errors do not echo response secrets."""
    with Subfork(
        KEY,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status, json={"detail": KEY}, headers={"Retry-After": "12"}
            )
        ),
    ) as client:
        with pytest.raises(error) as caught:
            client.graphs.list()
    assert caught.value.status_code == status
    assert caught.value.retry_after == "12"
    assert KEY not in str(caught.value)


def test_redirects_and_failed_writes_are_not_retried() -> None:
    """Verify redirects and failed writes are not retried."""
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        """Handle a mocked HTTP request for this scenario."""
        requests.append(request)
        return httpx.Response(307, headers={"Location": "https://other.example"})

    with Subfork(KEY, transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(APIError):
            client.graphs.create(name="Test", definition={"name": "Test"})
    assert len(requests) == 1


def test_authoring_requests_match_server_contract() -> None:
    """Verify authoring requests match server contract."""
    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        """Handle a mocked HTTP request for this scenario."""
        seen.append(
            (
                request.method,
                request.url.path,
                dict(request.url.params),
                json.loads(request.content) if request.content else None,
            )
        )
        return httpx.Response(200, json={"id": "g_test"})

    with Subfork(KEY, transport=httpx.MockTransport(handle)) as client:
        definition = {"name": "Demo", "nodes": [], "edges": []}
        client.graphs.validate(definition)
        client.graphs.create(name="Demo", definition=definition)
        client.graphs.update("g_test", name="Demo", definition=definition)
        client.graphs.publish("g_test", version="v1", interface={"inputs": {}, "outputs": {}})
        client.graphs.execute("g_test", version="v1", inputs={"value": 3})
    assert [row[:2] for row in seen] == [
        ("POST", "/api/v1/graphs/validate"),
        ("POST", "/api/v1/graphs"),
        ("PUT", "/api/v1/graphs/g_test"),
        ("POST", "/api/v1/graphs/g_test/versions"),
        ("POST", "/api/v1/graphs/g_test/execute"),
    ]
    assert seen[0][3] == {"name": "Demo", "definition": definition}
    assert seen[-2][3]["interface"] == {"inputs": {}, "outputs": {}}
    assert seen[-1][2:] == ({"version": "v1"}, {"inputs": {"value": 3}})


def test_transport_failure_is_not_retried() -> None:
    """Verify transport failure is not retried."""
    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        """Handle a mocked HTTP request for this scenario."""
        seen.append(request)
        raise httpx.ReadTimeout(KEY)

    with Subfork(KEY, transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(TransportError) as caught:
            client.graphs.execute("g_test")
    assert len(seen) == 1 and KEY not in str(caught.value)


@pytest.mark.parametrize("status", ["completed", "failed", "canceled", "outcome_unknown"])
def test_wait_returns_terminal_result(status: str) -> None:
    """Verify wait returns terminal result."""
    with Subfork(
        KEY,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"id": "e_test", "status": status})
        ),
    ) as client:
        assert client.executions.wait("e_test")["status"] == status


def test_wait_timeout_does_not_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify wait timeout does not cancel."""
    from subfork import resources

    ticks = iter([0, 0, 1, 2])
    monkeypatch.setattr(resources.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(resources.time, "sleep", lambda seconds: None)
    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        """Handle a mocked HTTP request for this scenario."""
        seen.append(request)
        return httpx.Response(200, json={"status": "running"})

    with Subfork(KEY, transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ExecutionTimeout):
            client.executions.wait("e_test", timeout=1)
    assert len(seen) == 1 and seen[0].method == "GET"
