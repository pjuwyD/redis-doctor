# Examples

Real commands with real output. The "bad" instance below was seeded with 400
`lock:*` keys without TTL, 120 `session:user:*` keys, and a few thousand padded
values under `noeviction` with no persistence — a deliberately unhealthy cache.

## A full `analyze` on an unhealthy instance

```bash
redis-doctor analyze redis://localhost:6379
```

```text
Redis Doctor Report
Target: redis://localhost:7799/0
Generated: 2026-06-18 07:42:16
Health score: 30/100
╭─────────────── Summary ────────────────╮
│ - Redis 7.0.15, role master, uptime 1s │
│ - Memory: 2.3 MB / 4.0 MB (56%)        │
│ - Clients: 1 connected, 0 blocked      │
│ - Policy: noeviction                   │
│ - Keys: 820                            │
╰────────────────────────────────────────╯
Key analysis based on sample:
- scanned 820 keys from estimated 820 total keys
- confidence: high
- scan duration: 0.001s
- complete scan: yes

        Top prefixes by count
┏━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━┓
┃  # ┃ Prefix         ┃ Keys ┃ Share ┃
┡━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━┩
│  1 │ session:user:* │  120 │   15% │
│  2 │ lock:200:*     │    1 │    0% │
│ …  │ …              │  …   │   …   │
└────┴────────────────┴──────┴───────┘
Type distribution: string 100%

3 critical  5 warning  1 info

Critical findings:
  [TTL] ttl.locks_without_ttl — 100% of lock:* keys have no TTL
    Evidence: no_ttl=400, total_in_category=400, share=1.0
    Impact: Locks without a TTL can deadlock workflows permanently if a holder dies.
    Checks: redis-cli TTL <key>
    Fixes: Set an appropriate EXPIRE/SETEX on these keys; Ensure code paths that
create them set a TTL
  [TTL] ttl.sessions_without_ttl — 100% of session/temp keys have no TTL
    Evidence: no_ttl=120, total_in_category=120, share=1.0
  [SECURITY] security.no_auth — Redis has no authentication configured
    Evidence: requirepass_set=False, default_user_nopass=True

Warnings:
  [MEMORY] memory.high_fragmentation — Memory fragmentation ratio is high (3.53)
  [CONFIG] config.risky_eviction_policy — maxmemory-policy is noeviction with a memory limit set
  [CONFIG] config.no_persistence — Neither RDB nor AOF persistence is enabled
  [PERSISTENCE] persistence.none_enabled — No persistence is enabled
  [SECURITY] security.default_user — The default user is enabled / widely used

Info:
  [SERVER] server.recent_restart — Redis restarted within the last hour
```

Every finding includes Evidence, Impact, Checks, and Fixes lines (trimmed above
for space).

## Keyspace-only report

```bash
redis-doctor scan-keys redis://localhost:6379
```

Prints the prefix-by-count and prefix-by-memory tables, the type distribution, and
the sampling metadata block — without running the other analyzers:

```text
Key analysis based on sample:
- scanned 820 keys from estimated 820 total keys
- confidence: high

        Top prefixes by count                    Top prefixes by memory
┏━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━┓          ┏━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃  # ┃ Prefix         ┃ Keys ┃          ┃  # ┃ Prefix         ┃  Memory ┃
┡━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━┩          ┡━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│  1 │ session:user:* │  120 │          │  1 │ session:user:* │ 13.9 KB │
└────┴────────────────┴──────┘          └────┴────────────────┴─────────┘
Type distribution: string 100%
```

## Config / persistence / replication only

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

## JSON for automation

```bash
redis-doctor analyze redis://localhost:6379 --format json --only server,memory
```

```json
{
  "target": "redis://localhost:6379/0",
  "redis_doctor_version": "1.0.0",
  "health_score": 85,
  "category_scores": { "server": 95, "memory": 90, "...": 100 },
  "summary": { "critical": 0, "warning": 3, "info": 0 },
  "server": {
    "redis_version": "7.4.7", "role": "master",
    "used_memory_bytes": 3330552, "maxmemory_bytes": 0
  },
  "findings": [ /* ... */ ]
}
```

Pipe it into `jq`:

```bash
redis-doctor analyze redis://localhost:6379 --format json \
  | jq -r '.findings[] | select(.severity=="critical") | .id'
```

## Compare two runs

```bash
redis-doctor analyze redis://localhost:6379 --format json --output before.json
# ... time passes ...
redis-doctor analyze redis://localhost:6379 --format json --output after.json
redis-doctor diff before.json after.json
```

```text
Since previous report:
- health score 85 -> 60 (-25)
- memory changed by +38% (+1240000 bytes)
- idle clients 44 -> 426
- stream live:Inform.stream grew by +122000 entries
- 2 new finding(s): clients.idle_many, streams.pending_high
```

## Focus on one module

```bash
redis-doctor analyze redis://localhost:6379 --only streams,clients
redis-doctor analyze redis://localhost:6379 --skip keyspace,ttl,bigkey,types
```

## A single stream, deeply

```bash
redis-doctor inspect-stream redis://localhost:6379 live:Inform.stream
```

```text
                              Streams
┃ Stream             ┃ Length ┃ Group         ┃ Pending ┃
│ live:Inform.stream │  384221 │ tr069-workers │   92440 │

Critical findings:
  [STREAMS] streams.pending_high — Group tr069-workers on live:Inform.stream has 92,440 pending messages
  [STREAMS] streams.idle_consumer_with_pending — Consumer worker-7 has 18,221 pending, idle 4h 12m
```

## CI gate

```bash
redis-doctor analyze "$REDIS_URL" --fail-on critical
echo "exit code: $?"   # 0 if healthy, 2 if any critical finding
```

See [Commands](commands/index.md) for the full flag reference and
[CI integration](guides/ci.md) for pipeline snippets.
