# Redis Doctor

**Diagnose the production health of a Redis deployment** — memory, keys, TTLs,
streams, clients, slow commands, replication, persistence, Sentinel, and Cluster —
and explain, for every problem found:

1. What is wrong?
2. Why is it risky?
3. How bad is it? (severity + evidence)
4. How do I verify it? (suggested checks)
5. How do I fix it? (suggested fixes)

Redis Doctor is **not** a data browser. It is a read-only production diagnostic
tool. It never runs a command that writes, deletes, mutates config, or kills
clients, and `KEYS`/`MONITOR` are blocked unconditionally. See [Safety](safety.md).

```bash
redis-doctor analyze redis://localhost:6379
```

```text
Redis health score: 72/100

Critical:
- 1.2M keys without TTL under prefix session:*
- Stream live:Inform.stream has 380k pending messages
- 426 idle clients older than 1h
- maxmemory-policy is noeviction while memory usage is 91%
```

## Documentation map

### Start here
- [Getting started](getting-started.md) — install and run your first diagnosis.
- [Installation](installation.md) — pip, pipx, Docker, standalone binary, extras.
- [Examples](examples.md) — real commands with real output.

### Reference
- [Commands](commands/index.md) — every subcommand and its flags.
- [Configuration](configuration.md) — the YAML file, env vars, precedence.
- [Findings catalog](findings-catalog.md) — every finding ID, severity, trigger.
- [Output formats & exit codes](output-and-exit-codes.md) — terminal/JSON/markdown/PDF, CI contract.
- [Safety guardrails](safety.md) — what the tool will and will not do.

### Guides
- [Explore](guides/explore.md) — browse keys read-only, with a lock for full values.
- [Terminal UI](guides/tui.md) — the interactive `tui`.
- [Web dashboard](guides/gui.md) — the local `serve` GUI + JSON API.
- [CI integration](guides/ci.md) — GitHub Actions, GitLab CI, Kubernetes CronJob.

### Developer
- [Architecture](developer/architecture.md) — pipeline, models, scoring.
- [Collectors](developer/collectors.md) and [Analyzers](developer/analyzers.md).
- [Rule engine](developer/rule-engine.md) — thresholds, enable/ignore.
- [Adding a module](developer/adding-a-module.md) — end-to-end recipe.
- [Testing](developer/testing.md) — unit + integration, the coverage gate.

## What it diagnoses

| Area | Examples of what it catches |
|---|---|
| Memory | high usage, `noeviction` near the limit, fragmentation |
| Keyspace | dominant prefixes, very large key counts, no-TTL share |
| TTL | locks/sessions/tokens without TTL, inconsistent TTLs |
| Big keys | huge strings, oversized collections |
| Streams | high pending, idle consumers, no consumers, lag |
| Clients | near maxclients, blocked, idle, unnamed, output buffers |
| Slowlog | dangerous O(N) commands, repeated slow patterns |
| Config | no maxmemory, risky eviction, `timeout=0`, no persistence |
| Persistence | failed RDB/AOF, loading, stale last-save |
| Replication | link down, lag, writable replica |
| Security | no auth, default user, protected-mode off |
| Sentinel | under-quorum, master disagreement, replica lag |
| Cluster | uncovered slots, failed nodes, imbalance |
