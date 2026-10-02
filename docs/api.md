# API reference and file workflows

The synchronous Python client returns dictionaries from the Subfork API. It does
not print results; the command-line tool's output options do not affect Python.
Set `SUBFORK_API_KEY`, then use a context manager to close connections reliably.

## Execute and inspect results

```python
from typing import Any, Dict
from subfork import Subfork


def run_graph(client: Subfork, graph_id: str) -> Dict[str, Any]:
    """Run a graph and return its completed outputs."""
    submitted = client.graphs.execute(graph_id)
    result = client.executions.wait(submitted["id"], timeout=300)
    if result["status"] != "completed":
        raise RuntimeError(f"Execution {submitted['id']}: {result['status']}")
    return result["outputs"]


with Subfork() as client:
    outputs = run_graph(client, "g_YOUR_GRAPH")
```

Output names and shapes are defined by each graph. Text and JSON can be used
immediately. A media output may contain an `artifact` object, a remote URL, or
inline data. Artifact download helpers accept an artifact ID, not arbitrary URLs.
Waiting requires `graphs:read`; starting a run requires `graphs:run`. A waiting
timeout does not cancel the remote execution.

## Download artifacts

For a graph exposing an `audio` media output with an artifact reference:

```python
with Subfork() as client:
    outputs = run_graph(client, "g_YOUR_GRAPH")
    artifact_id = outputs["audio"]["artifact"]["artifact_id"]
    path = client.artifacts.download(artifact_id, "narration.mp3")
```

A direct artifact output instead exposes `outputs["artifact"]["artifact_id"]`.
The helper works for PDFs, images, MP3, MP4 and other stored file types. It returns
`pathlib.Path`; it does not decode media or open a viewer. Use your preferred media
library or player after downloading.

`download(artifact_id, destination, *, overwrite=False, max_bytes=250_000_000)`
streams to a temporary file, then publishes the complete file at the requested
path. The parent directory must exist. Existing files are protected unless you
pass `overwrite=True`; failed downloads preserve them. The default decoded-byte
limit is 250 MB and can be increased explicitly.

Downloads require `graphs:read` and access to the artifact. Expired or deleted
artifacts cannot be recovered by the client. One HTTPS storage redirect is
supported; the Subfork authorization header and cookies are not forwarded.

## Upload graph assets

**Server requirement:** API-key asset upload/list support must be deployed.
Older servers return HTTP 403 even with an otherwise valid key.

```python
with Subfork() as client:
    uploaded = client.assets.upload(
        "g_YOUR_GRAPH", "document.pdf", content_type="application/pdf"
    )
    artifact_id = uploaded["artifact_id"]
    print(artifact_id)
```

`upload(graph_id, source, *, content_type=None)` streams a local file as multipart
form data. The MIME type is inferred from its filename unless supplied; the
server validates the file and controls persisted metadata. The returned JSON
includes `artifact_id`, `media_type`, `size_bytes` and other artifact metadata.

Uploads require `graphs:write`, an owned graph, enabled uploads and available
storage quota. The asset starts private. Uploading does **not** automatically
bind an Asset node or execute the graph. To select it on an existing Asset node:

```python
with Subfork() as client:
    graph_id = "g_YOUR_GRAPH"
    graph = client.graphs.get(graph_id)
    definition = graph["definition"]
    source_node = next(
        node for node in definition["nodes"]
        if node["node_instance_id"] == "pdf" and node["node_id"] == "n_asset"
    )
    uploaded = client.assets.upload(graph_id, "document.pdf")
    source_node["params"]["artifact_id"] = uploaded["artifact_id"]
    client.graphs.update(
        graph_id, name=graph["name"], definition=definition,
        description=graph.get("description") or "",
    )
```

The example changes the draft; existing published versions remain immutable.
Fetch the latest draft and avoid concurrent edits when updating its definition.
For a graph exposing an artifact input, you can instead supply the reference in
`graphs.execute(..., inputs={"pdf": {"artifact_id": artifact_id}})`. The input
name must match that graph's published or draft interface.

List assets with `client.assets.list(graph_id)`. It returns an `assets` array in a
JSON object. Use `include_generated=True` to include unexpired execution outputs.
Listing requires `graphs:read` and ownership of the graph.

The client does not expose secret management, asset deletion, visibility changes
or retention changes. Configure provider secrets through the Subfork UI.

## Errors and retries

HTTP failures raise `APIError` subclasses, including permission, validation and
rate-limit errors. Downloads may also raise `FileExistsError`, filesystem errors,
or `ValueError` for an invalid limit or oversized response. Network failures raise
`TransportError`. File transfers and graph executions are never automatically
retried: an upload or run may have succeeded before the connection failed. Inspect
remote state before repeating a write.
