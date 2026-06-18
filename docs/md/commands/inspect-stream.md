# inspect-stream

Deep diagnostic for a single named stream.

```bash
redis-doctor inspect-stream <redis-url> <stream> [options]
```

## What it does

Reads `XLEN`, `XINFO STREAM`, `XINFO GROUPS`, and `XINFO CONSUMERS` for the named
stream and runs the stream analyzer over it. Unlike `analyze`, it does **not**
sample the keyspace — it inspects exactly the stream you name, so it is cheap to
run against a known problem stream.

Emits the stream findings: `streams.length_high`, `streams.pending_high`,
`streams.idle_consumer_with_pending`, `streams.no_consumers`, `streams.lag_high`,
`streams.many_inactive_consumers`, `streams.no_groups`
(see the [catalog](../findings-catalog.md#streams)).

## Flags

[Connection flags](index.md#connection-flags) plus `--format` and `--output`.

## Example

```bash
redis-doctor inspect-stream redis://localhost:6379 live:Inform.stream
```

```text
                              Streams
┃ Stream             ┃ Length ┃ Group         ┃ Consumers ┃ Pending ┃
│ live:Inform.stream │  384221 │ tr069-workers │     1     │   92440 │

Critical findings:
  [STREAMS] streams.pending_high — Group tr069-workers on live:Inform.stream has 92,440 pending messages
    Checks: redis-cli XINFO GROUPS live:Inform.stream | redis-cli XPENDING live:Inform.stream tr069-workers
    Fixes: Scale up consumers; Reclaim stuck messages with XAUTOCLAIM
  [STREAMS] streams.idle_consumer_with_pending — Consumer worker-7 has 18,221 pending, idle 4h 12m
```

Remediation suggestions name `XAUTOCLAIM`, `XGROUP DELCONSUMER`, and `XTRIM` but
the tool never runs them — see [Safety](../safety.md).
