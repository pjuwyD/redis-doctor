# Terminal UI

An interactive terminal dashboard built with [Textual](https://textual.textualize.io/).
Requires the `tui` extra:

```bash
pip install 'redis-doctor[tui]'
redis-doctor tui redis://localhost:6379
```

It runs the same pipeline as [`analyze`](../commands/analyze.md), holds a single
`Report`, and lets you browse it interactively. Every panel renders a slice of the
one report — nothing is recomputed as you switch panels.

## Layout

A left sidebar of panels and a main content area:

```text
Health     - score, severity counts, top findings
Memory     - used vs maxmemory, fragmentation, policy, memory findings
Keys       - prefix table, type distribution, sampling metadata, key findings
Streams    - stream list with groups/consumers/pending
Clients    - client groupings (idle/blocked/unnamed/by-command)
Slowlog    - slowlog metrics + slowlog findings
Config     - config + persistence risk findings
Replication- role + replica topology
Sentinel   - Sentinel topology (when connected via Sentinel)
```

## Key bindings

| Key | Action |
|---|---|
| arrows / mouse | switch panels via the sidebar |
| `e` | expand the selected view's findings to show evidence, checks, and fixes |
| `f` | cycle the severity filter: all → critical → warning |
| `r` | re-run the full analysis and refresh every panel |
| `s` | save the current report to JSON (prompts for a path) |
| `q` | quit |

The analysis runs in a background worker so the UI stays responsive, and a render
error in one panel never tears down the app.
