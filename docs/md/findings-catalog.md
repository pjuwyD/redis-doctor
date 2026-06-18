# Findings catalog

Every finding the tool can emit has a **stable ID** (`category.name`). These IDs
are a contract: they are stable across versions, appear in JSON output, and are
what you reference in `rules:`/`ignore.rules` ([Configuration](configuration.md)).

Severities: **critical**, **warning**, **info**. Thresholds come from
configuration; the triggers below describe the default behavior.

## server

| ID | Severity | Trigger |
|---|---|---|
| `server.version_outdated` | warning | major version < 7 |
| `server.recent_restart` | info | uptime < 1h |
| `server.role_unexpected` | info | role differs from `--expect-role` |
| `server.high_client_count` | warning/critical | connected clients ≥ 80% / 95% of maxclients |
| `server.blocked_clients` | warning/critical | blocked clients ≥ warning / critical threshold |
| `server.evictions_occurring` | warning | evicted_keys > 0 |

## memory

| ID | Severity | Trigger |
|---|---|---|
| `memory.high_usage` | warning/critical | used ≥ warning/critical pct of maxmemory |
| `memory.high_usage_noeviction` | critical | policy `noeviction` and usage ≥ 85% |
| `memory.high_fragmentation` | warning | fragmentation ratio > threshold |
| `memory.rss_overhead` | warning | RSS much larger than used memory |

## keyspace

| ID | Severity | Trigger |
|---|---|---|
| `keyspace.dominant_prefix` | info | one prefix > 50% of the sample |
| `keyspace.high_key_count` | warning | very large DBSIZE with a high no-TTL share |

## ttl

| ID | Severity | Trigger |
|---|---|---|
| `ttl.locks_without_ttl` | critical | `lock:*`-style keys without TTL |
| `ttl.sessions_without_ttl` | critical | high share of session/temp keys without TTL |
| `ttl.tokens_without_ttl` | critical | OTP/token/reset keys without TTL |
| `ttl.cache_permanent` | warning | cache prefix dominated by permanent keys |
| `ttl.excessive_ttl` | warning | temporary-looking keys with TTL beyond expected max |
| `ttl.inconsistent_within_prefix` | warning | mixed TTL / no-TTL inside one prefix |

## bigkey

| ID | Severity | Trigger |
|---|---|---|
| `bigkey.huge_memory` | critical | key memory > `huge_key_mb` |
| `bigkey.big_memory` | warning | key memory > `big_key_mb` |
| `bigkey.huge_collection` | critical | element count > `huge_collection` |
| `bigkey.large_collection` | warning | element count > `large_collection` |

## types

| ID | Severity | Trigger |
|---|---|---|
| `types.mixed_under_prefix` | warning | one prefix contains unexpectedly mixed types |
| `types.untrimmed_collections` | info | growing list/zset/stream without TTL/trim |

## streams

| ID | Severity | Trigger |
|---|---|---|
| `streams.length_high` | critical | length > `stream_length_warning` |
| `streams.pending_high` | critical | group pending > `stream_pending_warning` |
| `streams.idle_consumer_with_pending` | critical | consumer idle > threshold AND pending > 0 |
| `streams.no_consumers` | critical | active group with zero consumers |
| `streams.lag_high` | warning | last-delivered id far behind the tail |
| `streams.many_inactive_consumers` | warning | many idle consumers |
| `streams.no_groups` | warning | stream exists with no consumer groups |

## clients

| ID | Severity | Trigger |
|---|---|---|
| `clients.idle_many` | warning/critical | idle count ≥ warning/critical count |
| `clients.output_buffer_large` | critical | a client output buffer is very large |
| `clients.unnamed` | warning | high share of clients with no name |
| `clients.same_ip_many` | warning | many clients from one IP |

## slowlog

| ID | Severity | Trigger |
|---|---|---|
| `slowlog.dangerous_command` | critical | `KEYS`, full `SORT`, `SMEMBERS`/`LRANGE` on huge sets |
| `slowlog.repeated_slow_command` | warning | same command pattern repeats often |
| `slowlog.length_near_max` | warning | slowlog length near slowlog-max-len |

## scripting

| ID | Severity | Trigger |
|---|---|---|
| `scripting.many_cached_scripts` | warning | `number_of_cached_scripts` over the threshold |
| `scripting.scripts_high_memory` | warning | script/function memory over the threshold |
| `scripting.long_running_script` | critical | a script/function is currently running (`FUNCTION STATS`) |
| `scripting.functions_registered` | info | registered Function libraries/functions (visibility) |
| `scripting.eval_inline_repeated` | warning | inline `EVAL` repeats in the slowlog (use EVALSHA/Functions) |

Note: legacy `EVAL`/`EVALSHA` scripts cannot be enumerated by Redis, so only the
cache count and memory are available; Functions (Redis 7.0+) are listed by name.

## latency

| ID | Severity | Trigger |
|---|---|---|
| `latency.spike` | warning | an event's max latency exceeds the threshold |
| `latency.fork_slow` | warning | fork latency high |
| `latency.aof_fsync_slow` | warning | aof-fsync latency high |

## config

| ID | Severity | Trigger |
|---|---|---|
| `config.no_maxmemory` | warning | maxmemory unset |
| `config.risky_eviction_policy` | warning | policy unsuited to workload |
| `config.timeout_zero_with_idle` | warning | `timeout=0` with many idle clients |
| `config.tcp_keepalive_bad` | info | keepalive disabled or very high |
| `config.slowlog_disabled` | warning | slowlog disabled or threshold absurdly high |

## persistence

| ID | Severity | Trigger |
|---|---|---|
| `persistence.rdb_failed` | critical | last RDB bgsave status is error |
| `persistence.aof_failed` | critical | AOF last write/rewrite status is error |
| `persistence.loading` | critical | instance is loading a dataset |
| `persistence.none_enabled` | warning | no persistence (acceptable for a pure cache) |
| `persistence.last_save_old` | warning | last save very old with many changes |

## replication

| ID | Severity | Trigger |
|---|---|---|
| `replication.link_down` | critical | replica link != up |
| `replication.lag_high` | warning/critical | replica lag ≥ warning/critical seconds |
| `replication.no_replicas` | warning | master has 0 replicas (when expected) |
| `replication.replica_writable` | critical | replica is not read-only |

## security

| ID | Severity | Trigger |
|---|---|---|
| `security.no_auth` | critical | no auth configured |
| `security.default_user` | warning | default user enabled / widely used |
| `security.protected_mode_off` | warning | protected-mode disabled |

## sentinel

| ID | Severity | Trigger |
|---|---|---|
| `sentinel.insufficient_quorum` | critical | reachable sentinels < quorum |
| `sentinel.replica_lag_high` | critical | a replica is far behind master |
| `sentinel.master_disagreement` | critical | sentinels disagree on the master |
| `sentinel.unreachable_replica` | warning | a replica is unreachable |
| `sentinel.failover_timeout_unusual` | warning | failover-timeout abnormally high |

## cluster

| ID | Severity | Trigger |
|---|---|---|
| `cluster.uncovered_slots` | critical | slots not assigned / state not ok |
| `cluster.failed_node` | critical | a node reports fail |
| `cluster.master_without_replica` | warning | a master has no replica |
| `cluster.uneven_keys` | warning | highly uneven key distribution |
| `cluster.uneven_memory` | warning | highly uneven memory distribution |
