# diff

Compare two saved JSON reports and show what changed. Does not connect to Redis.

```bash
redis-doctor diff <before.json> <after.json> [--format terminal|json] [--output <path>]
```

## What it computes

- Findings **added**, **removed**, and **unchanged**, matched by finding `id` plus
  the primary `affected` key.
- Health-score delta and per-category deltas.
- Key metric deltas: used memory, total keys, per-prefix key counts, per-stream
  length, and idle client count.

## Example

```bash
redis-doctor diff before.json after.json
```

```text
Since previous report:
- health score 85 -> 60 (-25)
- memory changed by +38% (+1240000 bytes)
- total keys changed by +84000
- idle clients 44 -> 426
- stream live:Inform.stream grew by +122000 entries
- 2 new finding(s): clients.idle_many, streams.pending_high
- 1 resolved finding(s): server.recent_restart
```

`--format json` emits the structured `Diff` object (added/removed/unchanged lists,
score and metric deltas) for automation. The same computation backs the web
dashboard's Diff view — see [the GUI guide](../guides/gui.md).
