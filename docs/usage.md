# Python usage

Use `Subfork` as a context manager to close its HTTP connection when finished.
Responses are ordinary dictionaries and lists.

```python
from subfork import Subfork

with Subfork() as client:
    graphs = client.graphs.list()
    nodes = client.nodes.list()
```

## Create and publish

Load a graph definition from JSON, validate it, and save a new graph:

```python
import json
from subfork import Subfork

with open("graph.json", encoding="utf-8") as stream:
    definition = json.load(stream)

with Subfork() as client:
    validation = client.graphs.validate(definition)
    if not validation.get("valid", False):
        raise ValueError(validation)
    graph = client.graphs.create(name="My graph", definition=definition)
    published = client.graphs.publish(graph["id"], version="v1")
```

Graphs are public. Publication creates an immutable version. To replace draft
content, use `client.graphs.update(graph_id, name=..., definition=..., description=...)`.
Supply the description you want to retain; omitting it clears the description.

## Execute and wait

```python
with Subfork() as client:
    execution = client.graphs.execute(graph_id, version="v1", inputs={})
    result = client.executions.wait(execution["id"], timeout=120)
    if result["status"] == "completed":
        print(result["outputs"])
    else:
        print("Execution ended:", result["status"])
```

Replace `graph_id` with your graph ID and `inputs` with its named inputs. Omit
`version` to run the draft. Runs consume your account's execution quota.

`execute()` submits immediately; `wait()` polls until a terminal state. You can
also call `executions.get(execution_id)` or `executions.cancel(execution_id)`.
A wait timeout stops polling without canceling the remote run.

## Discover reusable graphs

```python
with Subfork() as client:
    catalog = client.graphs.published()
    block = client.graphs.published_version(graph_id, "v1")
    interface = client.graphs.interface(owned_graph_id)
```

Published graph versions include a composite node manifest for use in larger
graphs. Pin versions to keep later publications from changing your graph.
See [examples](examples.md) for complete definitions.

## Handle errors

```python
from subfork import APIError, ExecutionTimeout, Subfork

try:
    with Subfork() as client:
        execution = client.graphs.execute(graph_id)
        result = client.executions.wait(execution["id"])
except APIError as error:
    print(error.status_code, str(error))
except ExecutionTimeout as error:
    print("Still waiting for:", error.execution_id)
```

API errors include `AuthenticationError`, `PermissionDeniedError`, `NotFoundError`,
`ValidationError`, and `RateLimitError`. The client does not automatically retry
requests. After a `TransportError`, check remote state before submitting another
create, publish, or execute request.

See [troubleshooting](troubleshooting.md) for common errors.
