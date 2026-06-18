# Explore

The Explore tab lets you **browse a Redis keyspace read-only** — list keys, see
each key's type/TTL/memory/size, and peek at contents — without giving up the
tool's safety guarantees. It is deliberately *not* a full data browser by default.

There are two tiers, and a lock between them:

| Tier | Default | Reads | Commands |
|---|---|---|---|
| **Metadata + bounded peek** | on | key metadata + a small, bounded sample of contents | `SCAN`, `TYPE`, `TTL`, `MEMORY USAGE`, `HSCAN`/`SSCAN`/`ZSCAN` `COUNT n`, `XRANGE COUNT n`, `GETRANGE`, `LINDEX` |
| **Full value read** | **locked** | the whole value (still capped) | `GET`, `HGETALL`, `SMEMBERS`, `LRANGE`, `ZRANGE`, … |

The lock is enforced in the [safety layer](../safety.md), not just the UI: full-read
commands belong to an "expensive read" tier that is refused unless the connection
was opened with the unlock. So even a bug in the UI cannot pull full values while
locked.

## In the web dashboard

Open `serve` ([web dashboard](gui.md)) and choose **Explore**:

1. Enter a target and an optional `MATCH` pattern (e.g. `session:*`), then **Scan**.
   Listing uses `SCAN` — never `KEYS`.
2. Click any key to see its metadata and a **bounded preview** (e.g. the first 25
   hash fields, a 4 KB slice of a string, a list's head and tail).
3. To see whole values, tick **🔒 full reads locked** to unlock it
   (**🔓 full reads UNLOCKED**). Subsequent key opens read the full value.
4. **Load more** pages through the keyspace.

Even when unlocked, full reads are **capped** (`FULL_MAX_ELEMENTS` elements; a full
string `GET` is refused above ~1 MB) so an unlock cannot pull an unbounded payload
or stall the server.

## Scripts & Functions

The **Scripts & Functions** button shows the server's scripting state. Note that
the **legacy script cache and Functions are two separate subsystems**: the cached
count and the number of Function libraries are unrelated and will usually differ.

- **Cached Lua scripts** — the *current* cache count (`number_of_cached_scripts`)
  and the memory the scripting subsystem uses. Redis provides no command to list
  cached `EVAL`/`EVALSHA` bodies, so the bodies are not shown (a Redis limitation,
  not the tool's). A count of `0` just means the cache is empty right now.
- **Usage since start** — because the cache count can be 0 even on a server that
  uses scripts heavily, the overview also shows cumulative `EVAL` / `EVALSHA` /
  `FCALL` call counts (from `INFO commandstats`) and the number of distinct scripts
  the slowlog happened to capture. This works even on Redis without FUNCTION
  support.
- **Functions** (Redis 7.0+) — each registered library with its functions and
  flags. The **source code** is shown only when you **unlock** (🔓), the same lock
  as full value reads; locked, you see names and flags but no code. The unlock is
  enforced server-side (`FUNCTION LIST WITHCODE` is only issued on an unlocked
  connection).

On Redis older than 7.0, only the cached-script summary is shown.

## JSON values

When a value is JSON (a string that parses as an object or array — common in
queues, event payloads, and caches), the preview renders it as a **collapsible
tree** rather than one long line:

- the top level is expanded and everything nested is collapsed; click a node to
  drill in;
- **expand all** / **collapse all** buttons and a **filter** box (matches keys and
  values, auto-expands and shows only matching paths) sit above the tree;
- each object/array node has a **copy** button (⧉) that copies that subtree as
  formatted JSON;
- a **raw** disclosure shows the exact original string.

JSON is also detected inside hash field values, list items, and stream field
values, where it renders as a collapsed tree with the same toolbar (filter,
expand/collapse, copy) right in the cell — handy for stream payloads. Non-JSON
strings show as plain wrapped text; if a bounded peek truncates a large JSON value
so it no longer parses, unlock and re-open the key to get the full, parseable
value.

## In the terminal UI

The [TUI](tui.md) has an **Explore** panel too, but because it holds a single
captured report and no live connection, it shows the **metadata of the largest
sampled keys** (type, TTL, memory, size) — no value peeking. Press `e` to show
more rows. For live browsing and value peeks, use the web dashboard.

## What it will not do

- It never uses `KEYS` or `MONITOR`.
- It never writes, deletes, or expires anything.
- Bounded peeks cannot return a whole large collection in one call.
- Full reads are gated behind an explicit unlock and still capped.

See [Safety](../safety.md) for the complete command policy.
