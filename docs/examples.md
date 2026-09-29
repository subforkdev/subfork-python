# Examples

Explore [examples.subfork.com](https://examples.subfork.com) for graphs covering
AI, data pipelines, dashboards, media, and more. Download definitions and read
their notes in the [subfork-examples repository](https://github.com/subforkdev/subfork-examples).
It's also the place to contribute examples for other builders.

## Hello from Python

This graph returns a string. It requires read, write, and run scopes.

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
    graph = client.graphs.create(name=name, definition=definition)
    execution = client.graphs.execute(graph["id"])
    result = client.executions.wait(execution["id"])
    print(result["status"], result.get("outputs"))
```

This creates a public graph and uses execution quota. To publish a reusable
version, call `client.graphs.publish(graph["id"], version="v1")` with publish scope.

## Load a community example

Download a `*.subfork.json` file from the examples repository and read its
adjacent `*.notes.md` file for required inputs, secrets, and provider setup.
These exports wrap the graph definition in a `definition` field:

```python
import json
from subfork import Subfork

with open("example.subfork.json", encoding="utf-8") as stream:
    exported = json.load(stream)
definition = exported["definition"]

with Subfork() as client:
    validation = client.graphs.validate(definition)
    if not validation.get("valid", False):
        raise ValueError(validation)
    graph = client.graphs.create(
        name=definition.get("name", "Imported example"),
        description=definition.get("description", ""),
        definition=definition,
    )
    print(graph["id"])
```

Configure any required secrets in the graph's settings before executing it.
The CLI accepts a raw definition, so extract `exported["definition"]` to a JSON
file before using `subfork create`. CLI exports already use that raw format.

Browse the [example catalog](https://examples.subfork.com) to choose your next graph.
