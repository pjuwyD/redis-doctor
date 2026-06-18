# Safety guardrails

Redis Doctor is **read-only by default** and is designed to be safe to run against
production. The guardrails below are enforced centrally in `safety.py` and are
consulted before any command runs, so no analyzer can issue an unsafe command even
by accident.

## Allowed (read-only)

`PING`, `INFO`, `CONFIG GET`, `DBSIZE`, `CLIENT LIST`, `CLIENT INFO`,
`SLOWLOG GET`, `SLOWLOG LEN`, `LATENCY LATEST`, `LATENCY DOCTOR`, `MEMORY STATS`,
`MEMORY USAGE`, `SCAN`, `TYPE`, `TTL`, `PTTL`, `STRLEN`, `LLEN`, `SCARD`, `ZCARD`,
`HLEN`, `XLEN`, `XINFO STREAM`, `XINFO GROUPS`, `XINFO CONSUMERS`, `SCRIPT EXISTS`,
`FUNCTION LIST`, `FUNCTION STATS`, `ACL WHOAMI`, `ACL LIST` (redacted), read-only
`SENTINEL` subcommands, read-only `CLUSTER` subcommands.

## Bounded reads (allowed by default)

For the [Explore](guides/explore.md) feature, a set of cursor- or range-bounded
reads is allowed by default: `HSCAN`, `SSCAN`, `ZSCAN`, `XRANGE`, `XREVRANGE`,
`GETRANGE`, `LINDEX`, `OBJECT ENCODING`. With a `COUNT`/range (which the Explore
service always passes) these cannot return a whole large value in one call.

## Full value reads — gated by an explicit unlock

Full-value reads (`GET`, `MGET`, `HGETALL`, `HKEYS`, `HVALS`, `LRANGE`,
`SMEMBERS`, `ZRANGE`, …) are O(N) and expose data, so they are blocked unless the
connection is explicitly unlocked (the Explore tab's lock toggle / an
`allow_expensive` connection). They are reads, never writes — `allow_write` does
**not** unlock them. Even when unlocked, the Explore service caps how much it
reads. See the [Explore guide](guides/explore.md).

## Never allowed — under any flag

`KEYS` and `MONITOR` are blocked unconditionally. Attempting them raises
`UnsafeCommandError`. The keyspace is explored only with `SCAN`.

## Blocked unless `--allow-write` (no command path uses this)

`FLUSHDB`, `FLUSHALL`, `CLIENT KILL`, `CONFIG SET`, `EVAL`, `EVALSHA`,
`SCRIPT LOAD/FLUSH/KILL`, `FUNCTION LOAD/DELETE/FLUSH`, `MEMORY PURGE`, `XTRIM`,
`XGROUP DELCONSUMER`, `XAUTOCLAIM`, `DEL`,
`EXPIRE`, and any other mutating command. Remediation suggestions may *name*
commands like `XTRIM` or `XAUTOCLAIM`, but the tool never runs them.

## Always

- **Every** Redis call is wrapped with a timeout (`--socket-timeout`, default 5s).
- **Credentials are redacted** from logs, reports, and the rendered target string.
  A password in a URL becomes `***`. `RedisTarget` stores only *whether* a password
  exists; the value is excluded from serialization entirely.
- **ACL output is aggressively redacted** — password hashes (`#...`) and inline
  passwords (`>...`) are masked before anything is stored or displayed.
- **Slowlog arguments are redacted** — `AUTH`/`HELLO` arguments and any
  high-entropy token are replaced with `***`.
- The keyspace is **sampled, not fully scanned**, and the report states the sample
  size and confidence.

## How it is enforced

The connection wrapper (`SafeRedis`) routes every command — including pipelined
batches — through `safety.check_command(...)` first. Analyzers receive this
wrapper, never a raw client, so the policy cannot be bypassed.

```text
analyzer ──► SafeRedis.execute("CONFIG", "GET", "maxmemory")
                     │
                     └─► safety.check_command("CONFIG", "GET", ...) ──► allowed
                     └─► safety.check_command("CONFIG", "SET", ...) ──► UnsafeCommandError
```

## Privacy

No telemetry. Nothing leaves the machine. The tool works fully offline /
air-gapped, and the web dashboard binds to `127.0.0.1` by default.
