# inspect-clients

Client analysis only.

```bash
redis-doctor inspect-clients <redis-url> [options]
```

## What it does

Reads `CLIENT LIST`, groups connections by address, name, user, db, command, age,
idle time, and flags, and emits the client findings:
`clients.near_maxclients`, `clients.blocked`, `clients.idle_many`,
`clients.output_buffer_large`, `clients.unnamed`, `clients.same_ip_many`
(see the [catalog](../findings-catalog.md#clients)).

## Flags

[Connection flags](index.md#connection-flags) plus `--format` and `--output`.

## Example

```bash
redis-doctor inspect-clients redis://localhost:6379
```

```text
╭──────────────── Clients ─────────────────╮
│ - 842 connected, 12 blocked, 426 idle over 1h │
│ - 97% of clients have no name set        │
│ - Top client commands: XREADGROUP 320, BLPOP 120, GET 98 │
╰──────────────────────────────────────────╯

Warnings:
  [CLIENTS] clients.idle_many — 426 clients idle longer than 3600s
  [CLIENTS] clients.unnamed — 97% of clients have no name set
```

`clients.unnamed` is a nudge to call `CLIENT SETNAME` in each service so you can
attribute connections during incidents.
