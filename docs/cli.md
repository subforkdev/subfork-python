# Command line

The `subfork` command uses the same `SUBFORK_API_KEY` as the Python client.
You can also invoke it with `python -m subfork`.

## Find and reuse graphs

```bash
subfork list
subfork get GRAPH_ID
subfork published
subfork versions GRAPH_ID
subfork interface GRAPH_ID
subfork export GRAPH_ID --output graph.json
```

Export writes the draft definition, ready for `create`. It does not include
published versions, tags, or the separate graph description.

## Create and publish

```bash
subfork validate graph.json
subfork create graph.json --name "My graph"
subfork publish GRAPH_ID --version v1
```

Replace `GRAPH_ID` with the ID returned by `create`. Definitions must be JSON
objects; use `-` instead of a filename to read from stdin. For example files from
the community repository, see [loading an example](examples.md#load-a-community-example).

## Execute

```bash
subfork execute GRAPH_ID
subfork execute GRAPH_ID --version v1 --inputs inputs.json
subfork execute GRAPH_ID -o results.json
subfork execute GRAPH_ID -o results.json --force
```

Execution waits for completion and prints JSON outputs. `-o` / `--out` writes
results to a file instead of stdout. Use `-f` / `--force` to overwrite an existing
file; this flag also works with `export`.

A yellow spinner shows active nodes. Finished nodes remain on stderr with their
final status. JSON results stay on stdout, so piping works normally:

```bash
subfork execute GRAPH_ID > results.json
```

| Option | Behavior |
| --- | --- |
| `--no-wait` | Return the submission ID and status immediately |
| `--raw` | Return the full execution snapshot |
| `--wait-timeout 300` | Wait up to 300 seconds; the default is 120 |
| `--poll-interval 1` | Poll every second; the default is 2 |

A timeout or interruption does not cancel the remote run. Set `NO_COLOR=1` to
disable colors. Redirected stderr uses plain text without animation.

## Help and exit codes

```bash
subfork --help
subfork execute --help
```

Exit code `0` means success, `1` means an operational error, failed validation,
unsuccessful execution, or wait timeout, and `2` means invalid command usage.
Interrupted execution returns `130`.
