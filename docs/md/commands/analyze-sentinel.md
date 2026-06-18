# analyze-sentinel

Sentinel topology diagnostic. Connects to one or more Sentinel nodes using
read-only `SENTINEL` subcommands.

```bash
redis-doctor analyze-sentinel \
  --sentinel-node host:port [--sentinel-node host:port ...] \
  --master-name <name> [options]
```

## Flags

```text
--sentinel-node host:port    (repeatable, required)
--master-name <name>         (required)
--password <redis-password>
--sentinel-password <sentinel-password>
--format terminal|markdown|json   --output <path>
--fail-on none|warning|critical   --no-fail
--config <file>
```

## What it checks

Monitored masters, current master address, sentinel count vs. quorum,
failover-timeout, down-after-milliseconds, replica flags and lag. Findings:
`sentinel.insufficient_quorum`, `sentinel.replica_lag_high`,
`sentinel.master_disagreement`, `sentinel.unreachable_replica`,
`sentinel.failover_timeout_unusual`
(see the [catalog](../findings-catalog.md#sentinel)).

## Example

```bash
redis-doctor analyze-sentinel --sentinel-node 127.0.0.1:26379 --master-name mymaster
```

```text
Critical findings:
  [SENTINEL] sentinel.insufficient_quorum — Only 1 Sentinel(s) reachable, but quorum is 2
    Evidence: reachable_sentinels=1, quorum=2
Warnings:
  [SENTINEL] sentinel.failover_timeout_unusual — failover-timeout is unusually high: 180000 ms
```
