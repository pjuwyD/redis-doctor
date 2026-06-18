# scan-keys

Keyspace and prefix report only — no other analyzers run.

```bash
redis-doctor scan-keys <redis-url> [options]
```

## What it does

Runs the [keyspace sampler](../developer/collectors.md#keyspace-sampler) (via
`SCAN`, never `KEYS`) and prints:

- sampling metadata (scanned vs. estimated total, confidence, duration);
- top prefixes by key count;
- top prefixes by estimated memory;
- the value-type distribution.

It always exits `0` on a successful run (it is informational).

## Flags

[Connection flags](index.md#connection-flags) plus the sampling flags:

```text
--format terminal|markdown|json    --output <path>
--sample-size --scan-count --max-scan-seconds
--prefix-depth --prefix-separators
```

## Prefix tokenization

Keys are grouped by their first `--prefix-depth` tokens, split on
`--prefix-separators` (default `:.|/_`). For `session:user:123` and
`queue:email:pending`:

- depth 1 → `session`, `queue`
- depth 2 → `session:user`, `queue:email`

## Example

```bash
redis-doctor scan-keys redis://localhost:6379 --prefix-depth 1
```

```text
Key analysis based on sample:
- scanned 820 keys from estimated 820 total keys
- confidence: high

        Top prefixes by count
┃  # ┃ Prefix         ┃ Keys ┃ Share ┃
│  1 │ session:user:* │  120 │   15% │
Type distribution: string 100%
```

See also [`analyze`](analyze.md), which includes this section plus all other
modules.
