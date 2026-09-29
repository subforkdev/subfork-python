<div class="gridline-home-hero">
  <a href="https://subfork.com">
    <img src="assets/subfork-banner.png" alt="Subfork" width="100%">
  </a>
</div>

# Subfork Python

The Python client for [Subfork](https://subfork.com). Discover nodes, build reusable
graphs, publish versions, and run them from your scripts, applications, or agents.

## Install

Requires Python 3.8+.

```bash
pip install subfork
```

## Connect

Create a key under **Account → API keys** in Subfork and set `SUBFORK_API_KEY` in
your environment. Grant the permissions your application needs: read, write, run,
and/or publish. Keep the key out of source files and graph definitions.

```python
from subfork import Subfork

with Subfork() as client:
    nodes = client.nodes.list()
    graphs = client.graphs.list()
```

The client reads `SUBFORK_API_KEY` and connects to [subfork.com](https://subfork.com).

## Command line

The package also installs `subfork` (or use `python -m subfork`). It reads
`SUBFORK_API_KEY` from your environment and prints JSON for use in scripts.

```bash
subfork list
subfork export GRAPH_ID --output graph.json
subfork validate graph.json
subfork create graph.json --name "My new graph"
subfork interface GRAPH_ID
subfork publish GRAPH_ID --version v1
subfork execute GRAPH_ID --version v1 --inputs inputs.json
```

Export writes a graph's draft definition, which can be passed directly to create.
It refuses to overwrite an existing file; omit `--output` to print to stdout.
Descriptions, tags, and published versions are not included in the export.
JSON input files must contain an object; use `-` to read from stdin.
Create makes a public draft, publish creates an immutable version, and execute
waits for completion and prints the graph outputs. Runs consume account quota.
Use `execute --no-wait` for a submission summary or `execute --raw` for the full
execution snapshot. Waiting requires read and run scopes; submission alone requires
run scope. `--wait-timeout` (default 120) and `--poll-interval` (default 2) are in
seconds. A timeout stops waiting without canceling the remote run.
A yellow spinner precedes `Graph <name> .......... Running`, with `Running` in
green. As status snapshots arrive, the line shows the currently running node titles
(or multiple titles for parallel nodes). Short-lived nodes may finish between polls.
Set `NO_COLOR` to disable colors. Progress goes to stderr; stdout remains JSON.
Redirected progress uses a single plain-text line.

Other commands include `get`, `published`, and `versions`. Use `--help` on any
command. Node discovery and execution monitoring are available through the Python API.

Errors go to stderr. Operational errors and failed validation return exit code 1;
usage errors return 2. Failed executions and wait timeouts also return exit code 1.

## Create and run a graph

This example creates a text-producing graph, publishes `v1`, and runs that version.
It requires read, write, publish, and run permissions. Graphs are public, and runs
use your account's execution quota.

```python
from subfork import Subfork

name = "Python greeting"
definition = {
    "name": name,
    "nodes": [{
        "node_instance_id": "hello",
        "node_id": "n_text_value",
        "node_version": "1.0.0",
        "title": "Hello",
        "params": {"text": "Hello from Python"},
    }],
    "edges": [],
    "graph_outputs": {
        "text": {"node_instance_id": "hello", "output_name": "text"},
    },
}

with Subfork() as client:
    client.graphs.validate(definition)
    graph = client.graphs.create(name=name, definition=definition)
    client.graphs.publish(graph["id"], version="v1")

    execution = client.graphs.execute(graph["id"], version="v1")
    result = client.executions.wait(execution["id"], timeout=120)
    print(result["status"], result.get("outputs"))
```

To test a draft before publishing, call `graphs.execute(graph_id)` without a
version. To update a draft, use `graphs.update()` with its name, definition, and
description; omitting the description clears it.

## Reuse building blocks

Explore published graphs and inspect their versioned interfaces:

```python
with Subfork() as client:
    blocks = client.graphs.published()
    block = client.graphs.published_version(graph_id, "v1")
```

Replace `graph_id` with the ID of a graph you want to use. Published graph versions
can be composed into larger graphs using the returned composite node manifest.
Pin child versions so later publications do not change your graph's behavior.

## Handle failures

HTTP failures raise `APIError` subclasses, including `AuthenticationError`,
`PermissionDeniedError`, `ValidationError`, and `RateLimitError`. These expose
`status_code` and an optional `retry_after` header.

`executions.wait()` returns failed and canceled runs as well as successful ones,
so check the returned status. An `ExecutionTimeout` stops polling but does not
cancel the remote run; use `executions.cancel(execution_id)` to request cancellation.

The client does not automatically retry requests. After a `TransportError`, check
remote state before repeating a create, publish, or execute request.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and code-quality checks.

## License

[BSD-3-Clause](LICENSE).
