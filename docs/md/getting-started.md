# Getting started

This page takes you from zero to a first health report in a few minutes.

## 1. Install

The fastest way is [pipx](https://pipx.pypa.io/) so the CLI lands on your PATH in
an isolated environment:

```bash
pipx install redis-doctor
```

Or plain pip:

```bash
pip install redis-doctor
```

For the interactive terminal UI or the web dashboard, install the matching extra:

```bash
pip install 'redis-doctor[tui]'   # Textual TUI
pip install 'redis-doctor[gui]'   # FastAPI dashboard + PDF export
```

See [Installation](installation.md) for Docker, the standalone binary, and the
system libraries WeasyPrint needs for PDF export.

## 2. Run your first diagnosis

Point `analyze` at any Redis URL:

```bash
redis-doctor analyze redis://localhost:6379
```

You will get a health score, a server summary, a sampled keyspace overview, and a
list of findings grouped by severity. Each finding explains what is wrong, why it
matters, and how to check and fix it. See the full walk-through in
[Examples](examples.md).

Supported connection targets:

```bash
redis-doctor analyze redis://localhost:6379
redis-doctor analyze rediss://redis.example.com:6379          # TLS
redis-doctor analyze redis://:password@localhost:6379/0       # legacy AUTH
redis-doctor analyze redis://user:password@localhost:6379/0   # ACL
redis-doctor analyze unix:///var/run/redis/redis.sock
```

The password is **never** printed and is redacted everywhere it could appear
(logs, the rendered target, reports). See [Safety](safety.md).

## 3. Make it a CI gate

`analyze` returns a meaningful exit code so you can fail a pipeline on problems:

```bash
redis-doctor analyze "$REDIS_URL" --fail-on critical
```

- exit `0` — healthy (no findings at/above the threshold)
- exit `2` — at least one critical finding

Full table in [Output & exit codes](output-and-exit-codes.md), copy-paste CI
snippets in [CI integration](guides/ci.md).

## 4. Tune it for your workload

Drop a `redis-doctor.yml` next to your project and pass `--config`:

```bash
redis-doctor analyze redis://localhost:6379 --config redis-doctor.yml
```

You can change thresholds, declare TTL expectations for your key patterns, disable
noisy rules, and ignore key prefixes. See [Configuration](configuration.md).

## Next steps

- Explore every subcommand in the [Commands reference](commands/index.md).
- Browse the [Findings catalog](findings-catalog.md) to see everything the tool
  can detect.
- If you want to extend it, start with [Architecture](developer/architecture.md).
