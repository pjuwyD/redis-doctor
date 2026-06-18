# Output formats & exit codes

## Formats

Choose with `--format` (or `output.format` in config). Write to a file with
`--output <path>`; otherwise output goes to stdout.

| Format | Flag | Description |
|---|---|---|
| Terminal | `--format terminal` (default) | Rich, color-coded by severity, with summary, keyspace tables, and findings. |
| JSON | `--format json` | The full `Report` model. Stable schema — this is the automation contract. |
| Markdown | `--format markdown` | Summary, server info, findings with evidence/checks/fixes, raw stats appendix. |
| PDF | via `serve` `/api/export/{id}.pdf` | Rendered from markdown with WeasyPrint. |

The `report` command re-renders a saved JSON report in any other format, and
`diff` compares two JSON reports. See [Commands](commands/index.md).

### Overview

Every report includes an at-a-glance **Overview** (`stats.overview`) rendered
identically by the CLI, TUI (Health panel), and GUI dashboard: total keys (with
type distribution), streams (and total pending), cached scripts / Functions,
clients (total / maxclients / blocked / unnamed) with a **client-state breakdown**,
memory, throughput (ops/sec and hit rate), evictions, and slowlog length.

The client-state breakdown (active / idle / blocked / closing / slow-consumer /
pubsub / monitor / replica-link) is Redis's *application-level* view from
`CLIENT LIST` — not kernel TCP states, which Redis does not expose.

In the GUI, the category chart shows only categories that have findings (a wall of
"100"s is noise); when everything is healthy the chart is hidden.

### JSON shape

```json
{
  "target": "redis://localhost:6379/0",
  "generated_at": "2026-06-16T15:42:10+02:00",
  "redis_doctor_version": "1.0.0",
  "health_score": 72,
  "category_scores": { "memory": 60, "clients": 80, "streams": 40 },
  "summary": { "critical": 2, "warning": 7, "info": 11 },
  "server": { "redis_version": "7.2.4", "role": "master",
              "used_memory_bytes": 9341553868, "maxmemory_bytes": 10737418240 },
  "findings": [
    {
      "id": "memory.high_usage_noeviction",
      "severity": "critical",
      "category": "memory",
      "title": "Redis memory usage is high with noeviction policy",
      "evidence": { "used_memory_pct": 91.2, "maxmemory_policy": "noeviction" },
      "suggested_checks": ["redis-cli INFO memory"],
      "suggested_fixes": ["Increase maxmemory", "Add TTLs", "Use a suitable eviction policy"]
    }
  ],
  "skipped": [],
  "stats": { }
}
```

Every finding carries: `id`, `severity`, `category`, `confidence`, `title`,
`explanation`, `evidence`, `suggested_checks`, `suggested_fixes`, and `affected`.
See the [Findings catalog](findings-catalog.md).

## Health score

A secondary summary of the findings (the findings themselves are the product):

```text
start at 100
each critical finding: -15
each warning finding:  -5
each info finding:      0
clamp to [0, 100]
```

The same formula is applied per category to produce `category_scores`; a category
with no findings scores 100.

## Suppressed findings

Findings muted with [`suppress`](commands/suppress.md) are removed from `findings`
and listed under `suppressed` in the report. They do **not** count toward the
health score, the severity summary, or the exit code, so a known issue can be
acknowledged for a window without breaking a CI gate.

## Exit codes

```text
0 = success; no findings at or above the --fail-on threshold
1 = findings at/above the warning threshold were present
2 = findings at/above the critical threshold were present
3 = connection / authentication error
4 = invalid config / invalid arguments
5 = internal error
```

`--fail-on` accepts `none` (default — always exit 0 on a successful run),
`warning`, or `critical`. `--no-fail` forces exit 0 regardless of findings.

| `--fail-on` | criticals present | only warnings present | clean |
|---|---|---|---|
| `none` | 0 | 0 | 0 |
| `warning` | 2 | 1 | 0 |
| `critical` | 2 | 0 | 0 |

This is the contract CI relies on — see [CI integration](guides/ci.md).

## Skipped modules

When a command is unavailable (ACL restriction, old version, missing module) the
analyzer records a *skipped module* note and the run continues. These appear under
`skipped` in JSON and a "Skipped" section in the terminal output, e.g.:

```text
Skipped:
- config_values: user lacks permission for config_values
- keyspace: MEMORY USAGE skipped for 14 keys: keys expired during scan
```
