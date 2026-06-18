# analyze

The primary command. Runs the full diagnostic pipeline and renders a report.

```bash
redis-doctor analyze <redis-url> [options]
```

## What it does

Runs all collectors and analyzers: server, memory, latency, config, persistence,
replication, keyspace, TTL, big-key, types, streams, clients, slowlog, and
security. Produces a health score and a list of [findings](../findings-catalog.md).

## Flags

In addition to the [connection flags](index.md#connection-flags):

```text
--format terminal|markdown|json      --output <path>
--fail-on none|warning|critical      --no-fail
--config <file>
--only <module,module,...>           run only these analyzer modules
--skip <module,module,...>           skip these analyzer modules
--sample-size --scan-count --max-scan-seconds
--prefix-depth --prefix-separators
--fleet <fleet.yml>                  run a fleet of targets (see below)
```

Module names for `--only`/`--skip`: `server`, `memory`, `latency`, `config`,
`persistence`, `replication`, `keyspace`, `ttl`, `bigkey`, `types`, `streams`,
`clients`, `slowlog`, `security`. The key-level modules (`ttl`, `bigkey`, `types`,
`streams`) automatically pull in the `keyspace` sample they depend on.

## Examples

```bash
# Human-readable report
redis-doctor analyze redis://localhost:6379

# JSON for automation
redis-doctor analyze redis://localhost:6379 --format json --output report.json

# Markdown to a file
redis-doctor analyze redis://localhost:6379 --format markdown --output report.md

# CI gate
redis-doctor analyze "$REDIS_URL" --fail-on critical

# Only the streams and clients modules
redis-doctor analyze redis://localhost:6379 --only streams,clients

# Larger sample, longer scan budget
redis-doctor analyze redis://localhost:6379 --sample-size 50000 --max-scan-seconds 60
```

See full output in [Examples](../examples.md).

## Fleet mode

`--fleet <fleet.yml>` runs every target sequentially and writes one combined JSON
document instead of a single report:

```yaml
# fleet.yml
targets:
  - name: prod-cache
    url: redis://cache-1:6379
  - name: prod-queue
    url: redis://queue-1:6379
```

```bash
redis-doctor analyze --fleet fleet.yml --output fleet.json
```

The combined document has an `instances` array, each with `name`, redacted
`target`, `score`, and the full `report` (or an `error` if that target was
unreachable). The web dashboard's Fleet view consumes the same idea — see
[the GUI guide](../guides/gui.md).

## Exit codes

Governed by `--fail-on`; see [Output & exit codes](../output-and-exit-codes.md).
