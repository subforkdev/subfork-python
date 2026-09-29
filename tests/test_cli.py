"""Verify CLI contracts using the real SDK with an isolated HTTP transport."""

import io
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from subfork import Subfork, cli


@pytest.fixture
def requests(monkeypatch: pytest.MonkeyPatch) -> list:
    """Capture requests and provide representative API responses."""
    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        """Return a graph or execution response for each request."""
        seen.append(request)
        if request.url.path.endswith("/graphs/g_test"):
            return httpx.Response(
                200, json={"definition": {"name": "Greeting", "nodes": [], "edges": []}}
            )
        if request.url.path.endswith("/graphs/validate"):
            return httpx.Response(200, json={"valid": False, "errors": ["No output"]})
        return httpx.Response(200, json={"id": "test", "status": "completed"})

    def factory(**kwargs: Any) -> Subfork:
        """Construct a real client without network access."""
        return Subfork("synthetic-key", transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(cli, "Subfork", factory)
    return seen


def test_export_create_roundtrip(requests: list, tmp_path: Path, capsys: Any) -> None:
    """Export definitions that create accepts, without leaking response metadata."""
    output = tmp_path / "graph.json"
    assert cli.main(["export", "g_test", "--output", str(output)]) == 0
    definition = json.loads(output.read_text())
    assert definition == {"name": "Greeting", "nodes": [], "edges": []}
    assert capsys.readouterr().out == ""
    assert cli.main(["create", str(output), "--name", "Copy", "--tag", "demo"]) == 0
    assert json.loads(requests[-1].content) == {
        "name": "Copy",
        "definition": definition,
        "description": "",
        "tags": ["demo"],
    }
    assert json.loads(capsys.readouterr().out)["id"] == "test"
    assert cli.main(["export", "g_test", "--output", str(output)]) == 1
    assert json.loads(output.read_text()) == definition


@pytest.mark.parametrize("content", ["[]", "invalid", '{"name":'])
def test_invalid_input_never_sends(
    requests: list, monkeypatch: pytest.MonkeyPatch, content: str, capsys: Any
) -> None:
    """Reject malformed or non-object definitions before any HTTP request."""
    monkeypatch.setattr("sys.stdin", io.StringIO(content))
    assert cli.main(["create", "-"]) == 1
    assert requests == []
    assert capsys.readouterr().err.startswith("subfork:")


def test_publish_and_execute(requests: list, tmp_path: Path) -> None:
    """Dispatch publication and execution input submission correctly."""
    assert cli.main(["publish", "g_test", "--version", "v1"]) == 0
    assert json.loads(requests[-1].content) == {"version": "v1", "comment": ""}
    inputs = tmp_path / "inputs.json"
    inputs.write_text('{"greeting": "hello"}')
    assert cli.main(["execute", "g_test", "--version", "v1", "--inputs", str(inputs)]) == 0
    assert requests[-1].url.params["version"] == "v1"
    assert json.loads(requests[-1].content) == {"inputs": {"greeting": "hello"}}


def test_validation_failure(requests: list, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    """Return a failing exit status while retaining validation diagnostics as JSON."""
    monkeypatch.setattr("sys.stdin", io.StringIO('{"nodes": []}'))
    assert cli.main(["validate", "-"]) == 1
    assert json.loads(capsys.readouterr().out)["valid"] is False


def test_help_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow help without constructing an authenticated client."""
    monkeypatch.delenv("SUBFORK_API_KEY", raising=False)
    with pytest.raises(SystemExit) as result:
        cli.main(["--help"])
    assert result.value.code == 0


@pytest.mark.parametrize("status", [401, 403])
def test_api_error_is_safe(monkeypatch: pytest.MonkeyPatch, capsys: Any, status: int) -> None:
    """Report failed API calls without echoing server bodies or credentials."""

    def factory(**kwargs: Any) -> Subfork:
        """Create a client whose server returns a sensitive error body."""
        return Subfork(
            "synthetic-key",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status, text="sensitive body")
            ),
            **kwargs,
        )

    monkeypatch.setattr(cli, "Subfork", factory)
    assert cli.main(["list"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(status) in captured.err
    if status == 401:
        assert "SUBFORK_API_KEY" in captured.err
        assert "does not load .env" in captured.err
    assert "sensitive" not in captured.err
    assert "synthetic-key" not in captured.err


@pytest.mark.parametrize("command", ["graphs", "nodes", "executions"])
def test_removed_groups(command: str) -> None:
    """Reject removed resource groups as usage errors."""
    with pytest.raises(SystemExit) as result:
        cli.main([command])
    assert result.value.code == 2


@pytest.mark.parametrize("mode", ["default", "raw", "no-wait", "failed", "timeout"])
def test_execution_output_modes(monkeypatch: pytest.MonkeyPatch, capsys: Any, mode: str) -> None:
    """Wait for results by default and preserve explicit diagnostic output modes."""
    seen = []
    completed = {
        "id": "e_test",
        "status": "completed",
        "outputs": {"response": ["https://example.com"]},
        "definition": {"nodes": []},
    }
    if mode == "failed":
        completed["status"] = "failed"

    def handle(request: httpx.Request) -> httpx.Response:
        """Simulate asynchronous submission followed by completion."""
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"id": "e_test", "status": "running", "outputs": {}})
        return httpx.Response(200, json=completed)

    def factory(**kwargs: Any) -> Subfork:
        """Construct a client with mocked transport and optional wait timeout."""
        client = Subfork("synthetic-key", transport=httpx.MockTransport(handle), **kwargs)
        if mode == "timeout":

            def timeout(*args: Any, **kwargs: Any) -> dict:
                """Simulate reaching the waiting deadline without canceling."""
                from subfork import ExecutionTimeout

                raise ExecutionTimeout("e_test")

            monkeypatch.setattr(client.executions, "wait", timeout)
        return client

    monkeypatch.setattr(cli, "Subfork", factory)
    arguments = ["execute", "g_test"]
    if mode in {"raw", "no-wait"}:
        arguments.append("--" + mode)
    assert cli.main(arguments) == (1 if mode in {"failed", "timeout"} else 0)
    captured = capsys.readouterr()
    assert sum(request.method == "POST" for request in seen) == 1
    if mode == "timeout":
        assert captured.out == ""
        assert "e_test" in captured.err and "not canceled" in captured.err
        return
    output = json.loads(captured.out)
    if mode == "raw":
        assert output == completed
    elif mode == "default":
        assert output == completed["outputs"]
    else:
        assert output == {
            "execution_id": "e_test",
            "status": "failed" if mode == "failed" else "running",
        }
    assert len(seen) == (1 if mode == "no-wait" else 2)
