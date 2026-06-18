# config-check

Configuration, persistence, and replication risk only.

```bash
redis-doctor config-check <redis-url> [options]
```

## What it does

Runs the `config`, `persistence`, and `replication` analyzers (plus the `server`
module so the summary header is populated). Useful as a fast, key-independent
safety check that does not sample the keyspace.

Emits findings from the [config](../findings-catalog.md#config),
[persistence](../findings-catalog.md#persistence), and
[replication](../findings-catalog.md#replication) categories.

## Flags

[Connection flags](index.md#connection-flags) plus `--format`, `--output`,
`--fail-on`, `--no-fail`.

## Example

```bash
redis-doctor config-check redis://localhost:6379
```

```text
Health score: 85/100
0 critical  3 warning  1 info

Warnings:
  [CONFIG] config.risky_eviction_policy — maxmemory-policy is noeviction with a memory limit set
  [CONFIG] config.no_persistence — Neither RDB nor AOF persistence is enabled
  [PERSISTENCE] persistence.none_enabled — No persistence is enabled
```
