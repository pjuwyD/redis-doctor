# Collectors

A **collector** reads data from Redis and returns raw model objects. It never
produces findings — that is the [analyzer](analyzers.md)'s job.

## The contract

```python
from redis_doctor.collectors.base import Collector

class MyCollector(Collector):
    name = "mymodule"

    def collect(self, ctx) -> SomeModel | None:
        raw = ctx.redis.execute("INFO", "everything")  # guarded read
        return parse(raw)
```

- `name` is the key under which the result is stored: `ctx.collected[name]`.
- `collect(ctx)` returns a model object (or `None`).
- The base class wraps `collect()` in `run()`, which catches
  `redis.ResponseError` (ACL/permission/unknown-command) and connection/timeout
  errors, records a `SkippedModule`, and returns `None`. **Do not** swallow those
  yourself — let the base handle graceful degradation.

## Reading Redis safely

Use `ctx.redis` (a `SafeRedis`). Every command is checked against the
[safety policy](../safety.md) before it runs:

```python
ctx.redis.execute("CONFIG", "GET", "maxmemory")     # single command
ctx.redis.pipe([("TYPE", k), ("TTL", k)])            # guarded pipeline
```

`pipe()` runs many read commands in one round trip and returns per-command
results (errors come back as values, not exceptions), which is how the keyspace
sampler enriches thousands of keys efficiently.

## Shared INFO

`ctx.info_fields()` returns the parsed `INFO` dict, fetching it once and caching it
on the context. Several collectors (memory, persistence, replication) read from it
instead of issuing their own `INFO`.

## Keyspace sampler

`collectors/keyspace.py` is the most involved collector and the foundation for the
key-level analyzers. It:

- explores the keyspace with `SCAN` + `COUNT` (never `KEYS`);
- stops when **any** limit is hit — `sample_size` keys or `max_seconds`;
- excludes `ignore.keys` patterns;
- enriches each sampled key **in one pass** with `TYPE`, `TTL`, `MEMORY USAGE`, and
  the type-appropriate size command (`STRLEN`/`LLEN`/`SCARD`/`ZCARD`/`HLEN`/`XLEN`)
  via pipelined batches;
- records `KeySample.complete` and a confidence level (`high` if ≥50% of DBSIZE or
  the DB is small, `medium` if 5–50%, `low` if <5%);
- groups keys into prefixes by `prefix_depth`/`prefix_separators`.

Because the sample already carries type/TTL/memory/element-count, the `ttl`,
`bigkey`, and `types` analyzers need **no** extra Redis reads — they are
analyzer-only modules that read `ctx.collected["keyspace"]`.

## Where collected data is exposed

Collectors may also stash a render-friendly summary into `report.stats` (done in
`pipeline._build_stats`) so the terminal/TUI/GUI can show prefix tables, client
groupings, stream tables, etc., without re-deriving them.

## Existing collectors

`info`, `memory`, `latency`, `config_values`, `persistence`, `replication`,
`keyspace`, `streams`, `clients`, `slowlog`, `security` (registry); `sentinel`,
`cluster` (standalone).
