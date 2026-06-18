# analyze-cluster

Redis Cluster diagnostic, using read-only `CLUSTER` subcommands.

```bash
redis-doctor analyze-cluster <redis-url> [options]
```

## What it does

Detects whether the instance is in cluster mode. If it is not, it prints a notice
and exits `0`. If it is, it reports slot coverage and a per-node summary
(role, slots, keys, memory, clients) and emits the cluster findings:
`cluster.uncovered_slots`, `cluster.failed_node`, `cluster.master_without_replica`,
`cluster.uneven_keys`, `cluster.uneven_memory`
(see the [catalog](../findings-catalog.md#cluster)).

Per-node memory/keys are gathered by connecting to each master node and reading
`INFO`/`DBSIZE`; unreachable nodes are marked and skipped.

## Flags

```text
--host --port --password --tls
--socket-timeout --connect-timeout
--format terminal|markdown|json   --output <path>
--fail-on none|warning|critical   --no-fail
--config <file>
```

## Example

```bash
redis-doctor analyze-cluster redis://localhost:7000
```

```text
Cluster state: ok; slots 16384/16384 assigned (0 uncovered); 6 nodes, size 3

                         Cluster nodes
┃ Node            ┃ Role   ┃ Slots ┃ Keys   ┃ Memory  ┃ Clients ┃
│ 10.0.0.1:7000   │ master │  5461 │ 120000 │ 220 MB  │   42    │
│ 10.0.0.2:7001   │ master │  5461 │ 118500 │ 215 MB  │   39    │
│ 10.0.0.3:7002   │ master │  5462 │  60000 │ 110 MB  │   18    │

Warnings:
  [CLUSTER] cluster.uneven_keys — Uneven key distribution across masters
```

Against a non-cluster instance:

```text
This instance is not running in cluster mode.
```
