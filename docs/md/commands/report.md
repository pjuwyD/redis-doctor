# report

Re-render a previously saved JSON report in another format. Does not connect to
Redis.

```bash
redis-doctor report <input.json> [--format terminal|markdown|json] [--output <path>]
```

## Why

The JSON format is the [stable contract](../output-and-exit-codes.md). Save it
once in CI or from the [web dashboard](../guides/gui.md), then render it for humans
later without re-running the analysis.

## Example

```bash
redis-doctor analyze redis://localhost:6379 --format json --output report.json
redis-doctor report report.json --format markdown --output report.md
redis-doctor report report.json                       # terminal
```

If the file is missing or not a valid `Report`, the command exits `4`
(invalid argument). See [Output & exit codes](../output-and-exit-codes.md).
