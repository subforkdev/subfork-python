<div class="gridline-home-hero">
  <a href="https://subfork.com">
    <img src="https://raw.githubusercontent.com/subforkdev/subfork-python/master/assets/subfork-banner.png" alt="Subfork" width="100%">
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

The package includes a `subfork` CLI that uses your `SUBFORK_API_KEY`.

```bash
subfork list
subfork export GRAPH_ID --output graph.json
subfork validate graph.json
subfork create graph.json --name "My new graph"
subfork publish GRAPH_ID --version v1
subfork execute GRAPH_ID --version v1
subfork execute GRAPH_ID -o results.json
```

`execute` waits for completion and returns JSON. Use `-o` to save results to a
file; progress stays on stderr. Add `-f` / `--force` to overwrite existing output
files with `execute` or `export`. Run `subfork --help` or `subfork execute --help`
for more options.

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

## Documentation

See the [documentation](docs/index.md) for installation, Python usage, CLI options,
and examples. Browse [Subfork Examples](https://examples.subfork.com) and the
[subfork-examples repository](https://github.com/subforkdev/subfork-examples) for
graphs to learn from and reuse.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and code-quality checks.

## License

[BSD-3-Clause](LICENSE).
