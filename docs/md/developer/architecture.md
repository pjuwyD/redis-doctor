# Architecture

This page explains how the pieces fit together so you can extend the tool with
confidence. For a step-by-step recipe, jump to
[Adding a module](adding-a-module.md).

## The shape of a run

```text
CLI (Typer)
  └─ parse target + config            connection.py, config.py
  └─ connect() -> SafeRedis           connection.py + safety.py
  └─ run_pipeline(safe, config)       pipeline.py
        ├─ collect phase  : every Collector reads Redis -> ctx.collected[name]
        ├─ analyze phase  : every Analyzer reads ctx.collected -> [Finding]
        ├─ rule engine    : drop findings whose rule is disabled/ignored
        └─ assemble Report: score, category scores, summary, stats
  └─ emit_report(report, fmt, output) output/*.py
  └─ exit code                        from --fail-on
```

## Core principle: findings are the product

Every analyzer's real output is a list of `Finding` objects with stable IDs
(see the [findings catalog](../findings-catalog.md)). The health score, terminal
text, markdown, JSON, TUI, and GUI are all just *renderings* of findings. If you
add detection logic, you are adding findings.

## Data model

All models are Pydantic v2 and JSON-serializable; they are the only types that
cross module boundaries.

- **`Finding`** — `id`, `severity`, `category`, `confidence`, `title`,
  `explanation`, `evidence` (machine-readable facts), `suggested_checks`,
  `suggested_fixes`, `affected`.
- **`Report`** — target (redacted), timestamp, version, duration, `sampled`,
  `health_score`, `category_scores`, `summary`, `server`, `findings`, `skipped`,
  `stats`.
- **`RedisTarget`** — parsed connection params; stores *whether* a password
  exists, never the value (it is excluded from serialization).
- Supporting models: `ServerInfo`, `MemoryStats`, `KeySample`/`KeyInfo`,
  `StreamInfo`/`StreamGroup`/`StreamConsumer`, `ClientInfo`, `SlowlogEntry`.

## The pipeline

`pipeline.py` owns the orchestration:

- **`_registry()`** lists `ModuleSpec(name, collector, analyzer)` entries in run
  order. **Each module is added here.** A module may be collector-only,
  analyzer-only, or both.
- **Collect phase runs fully before the analyze phase.** This means analyzers can
  cross-read any other module's collected data via `ctx.collected[...]` regardless
  of registry order. For example, the persistence analyzer reads the `config`
  collector's values.
- **`RunContext`** is the shared state: the `SafeRedis` client, the `Config`, the
  `RuleEngine`, `collected` results, `skipped` notes, cached INFO fields, and CLI
  `options`.
- **`_DEPENDENCIES`** pulls in a prerequisite collector — e.g. `ttl`, `bigkey`,
  `types`, and `streams` depend on the `keyspace` sample. `disable_dependencies`
  skips this (used by [`inspect-stream`](../commands/inspect-stream.md), which
  names one stream and does not want a full keyspace scan).
- **Resilience**: a collector that hits an ACL/permission error records a
  `SkippedModule` and returns `None`; an analyzer that raises is caught and
  recorded. One failing module never aborts the run.

Sentinel and Cluster are **not** in the registry — they are standalone
(`collect_sentinel`/`analyze_sentinel`, `collect_cluster`/`analyze_cluster`) and
assemble a report with `build_report()`, because they connect differently
(multiple Sentinel nodes; per-node cluster connections).

## Scoring

`scoring.py` implements the score: start at 100, −15 per critical, −5 per warning,
0 per info, clamped to `[0, 100]`. The same formula per category yields
`category_scores`. See [Output & exit codes](../output-and-exit-codes.md#health-score).

## Project layout

```text
redis_doctor/
  cli.py            Typer app; all subcommands
  connection.py     RedisTarget parsing, connect(), SafeRedis wrapper
  safety.py         command allow/deny lists
  config.py         config loading + schema
  pipeline.py       collect -> analyze -> score -> Report, build_report()
  scoring.py        health score
  rule_engine.py    rule pack + overrides + enable/ignore
  models/           Pydantic models
  collectors/       read Redis -> model objects
  analyzers/        model objects -> findings
  output/           terminal, json, markdown, pdf
  history/          SQLite store + diff
  notify/           slack, email, webhook
  tui/              Textual app + panels
  gui/              FastAPI server + static SPA
rules/default.yml   shipped rule pack
```

## See also

- [Collectors](collectors.md) and [Analyzers](analyzers.md)
- [Rule engine](rule-engine.md)
- [Adding a module](adding-a-module.md)
- [Testing](testing.md)
