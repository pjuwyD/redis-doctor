# Commands

Every subcommand. All commands that touch Redis accept the
[connection flags](#connection-flags) and `--config`.

| Command | Purpose |
|---|---|
| [`analyze`](analyze.md) | Full diagnostic run (the primary command). |
| [`scan-keys`](scan-keys.md) | Keyspace + prefix report only. |
| [`inspect-stream`](inspect-stream.md) | Deep single-stream diagnostic. |
| [`inspect-clients`](inspect-clients.md) | Client analysis only. |
| [`config-check`](config-check.md) | Config + persistence + replication risk only. |
| [`analyze-sentinel`](analyze-sentinel.md) | Sentinel topology diagnostic. |
| [`analyze-cluster`](analyze-cluster.md) | Cluster diagnostic. |
| [`report`](report.md) | Re-render a saved JSON report in another format. |
| [`diff`](diff.md) | Diff two saved JSON reports. |
| `tui` | Interactive terminal UI — see [the TUI guide](../guides/tui.md). |
| `serve` | Web GUI + JSON API — see [the GUI guide](../guides/gui.md). |
| `version` | Print the version. |

## Connection flags

Accepted by every command that connects to Redis:

```text
<redis-url>                      redis://, rediss://, or unix:// (positional)
--host --port --db --username --password
--tls --tls-ca-cert --tls-cert --tls-key
--socket-timeout (default 5)     --connect-timeout (default 5)
--config <file>
```

A `<redis-url>` and explicit flags can be combined; flags override the URL.
Passwords also come from `REDIS_DOCTOR_PASSWORD`. The password is never printed —
see [Safety](../safety.md).

## Common output flags

Where applicable: `--format terminal|markdown|json`, `--output <path>`,
`--fail-on none|warning|critical`, `--no-fail`. See
[Output & exit codes](../output-and-exit-codes.md).
