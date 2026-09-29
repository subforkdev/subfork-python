# Troubleshooting

## 401: authentication failed

Check that `SUBFORK_API_KEY` is exported and is an active key from your Subfork
account. The client does not automatically read `.env` files. Create a replacement
under **Account → API keys** if the key has expired or been revoked.

## 403: operation not permitted

Check the key's scopes. Waiting for execution results needs `graphs:read` as well
as `graphs:run`. See [permissions](installation.md#choose-permissions).

## 404: graph not found

Check the graph ID and ownership. Reading a public graph does not give you
permission to modify, publish, or execute the original. Create your own copy first.

## 409: graph secret cannot be decrypted

Re-enter and save the affected secret in **Graph Settings → Secrets**, then retry.
This is a stored graph credential, separate from the key used by the Python
client. Other 409 responses can indicate a different execution setup conflict.

## Output file already exists

Use `-f` / `--force` to overwrite it:

```bash
subfork execute GRAPH_ID -o results.json --force
```

## Execution timed out or failed

A wait timeout stops the client from polling; the run may still be active. Use
`client.executions.get(execution_id)` to inspect it, or open the graph in Subfork.
Use `client.executions.cancel(execution_id)` if you want to cancel it.

A terminal `failed` state is different from a timeout. Inspect the execution
snapshot or the graph's execution history for node errors. The CLI's `--raw`
option includes the full snapshot when submitting a run.
