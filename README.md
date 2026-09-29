# subfork

Python API client for Subfork graph authoring, publication and execution.
**Alpha scaffold; not yet published to PyPI.** Distribution and import name: `subfork`.
BYO workers belong in the separate worker package, not this client.

## Development install

Requires Python 3.10+ and a modern pip (21.3+ for editable installs).
Use a supported interpreter explicitly; the system `python3` may be older.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
pytest
python -m build
python -m twine check dist/*
```

If pip reports that editable mode requires `setup.py`, check `python --version`
and `python -m pip --version`. Python 3.8 is unsupported. Create a new environment
with Python 3.10+ and upgrade pip there; upgrading pip alone cannot change its
Python interpreter. A `setup.py` compatibility shim is not needed.

With [uv](https://docs.astral.sh/uv/), a supported Python can also be provisioned
without changing the system Python. Preserve an existing environment by using a
new directory:

```bash
uv venv --python 3.12 .venv312
source .venv312/bin/activate
uv pip install -e '.[dev]'
```

Licensed under [BSD-3-Clause](LICENSE). CI builds and checks distributions but does
not publish them.

## Usage

Create an API key under Account → API keys on a deployment with API-key support.
Set `SUBFORK_API_KEY` in your process environment; never put it in source files,
URLs, graph definitions, notebooks committed to git, or agent transcripts.

```python
from subfork import Subfork

with Subfork() as client:  # Reads SUBFORK_API_KEY; defaults to https://subfork.com
    nodes = client.nodes.list(include_all_versions=True)
    graphs = client.graphs.list()
```

For a local deployment:

```python
with Subfork(base_url="http://subfork.localhost") as client:
    nodes = client.nodes.list()
```

`base_url` is an origin, without `/api/v1`. HTTPS is required except for loopback
and `.localhost` hosts. Credentials are sent in the Authorization bearer header.
Redirects are not followed. Use a context manager or call `client.close()`.

## Author, publish, execute

The following deliberately creates and publishes a public graph and consumes
execution quota. Grant read/write/run/publish scopes only when needed.
Responses are dictionaries preserving the server's JSON shape.

```python
from subfork import Subfork

name = "Python greeting"
definition = {
    "name": name,
    "nodes": [{
        "node_instance_id": "hello", "node_id": "n_text_value",
        "node_version": "1.0.0", "title": "Hello",
        "params": {"text": "Hello from Python"},
    }],
    "edges": [],
    "graph_outputs": {"text": {"node_instance_id": "hello", "output_name": "text"}},
}
with Subfork() as client:
    client.graphs.validate(definition)
    graph = client.graphs.create(name=name, definition=definition)
    client.graphs.publish(graph["id"], version="v1")
    execution = client.graphs.execute(graph["id"], version="v1")
    result = client.executions.wait(execution["id"], timeout=120)
    print(result["status"], result.get("outputs"))
```

Discover published blocks with `graphs.published()` and retrieve their exact
interfaces with `graphs.published_version(graph_id, version)`. Compose their
returned node IDs with `composite_graph` parameters and explicit pinned versions.
`graphs.interface(graph_id)` previews the server-inferred interface.
`graphs.update()` replaces the submitted draft fields, including description;
pass the description to preserve it. Existing server ownership and quotas apply.

## Errors and limits

Catch `AuthenticationError`, `PermissionDeniedError`, `ValidationError`,
`RateLimitError`, or the base `APIError`; HTTP errors expose `status_code` and
`retry_after`. Messages intentionally do not echo raw response bodies or secrets.
`TransportError` means the outcome of a write may be unknown. There are no automatic
retries: inspect remote state before retrying create, publish or execute operations.

`executions.wait()` polls until a terminal status and returns failed executions
as results too. `ExecutionTimeout` does **not** cancel the remote execution;
use `executions.cancel(id)` explicitly. Polling uses a monotonic deadline and caps
individual HTTP timeout settings by remaining time. HTTPX timeouts apply per I/O
phase, not a strict wall-clock deadline for the entire network exchange.

The first scaffold is synchronous. Async support, rich response models, artifact
streaming, idempotent write retries and worker support are not included. Mock HTTP
tests do not certify any particular server deployment.
