# Installation

Requires Python 3.8 or later.

```bash
pip install subfork
```

This installs the Python package and the `subfork` command. Both connect to
[subfork.com](https://subfork.com).

## Set your API key

Create a key in **Account → API keys**, then set it in your environment:

```bash
export SUBFORK_API_KEY="your-api-key"
subfork list
```

The client reads exported environment variables; it does not load `.env` files
automatically. Keep your key out of source files and graph definitions.

## Choose permissions

| Scope | Allows |
| --- | --- |
| `graphs:read` | Read accessible graphs, discover nodes, and inspect your executions |
| `graphs:write` | Create and update your graphs, and validate definitions |
| `graphs:run` | Execute your graphs and cancel your executions |
| `graphs:publish` | Publish versions of your graphs |

The CLI's default execution workflow needs both read and run permissions because
it waits for the result. Keys act as their owning account; scopes do not grant
permission to modify other users' graphs. Public graphs can be read and reused.

## Check the connection

```python
from subfork import Subfork

with Subfork() as client:
    for graph in client.graphs.list():
        print(graph["id"], graph["name"])
```

Continue with [Python usage](usage.md) or the [CLI](cli.md).
