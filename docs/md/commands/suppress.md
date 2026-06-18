# suppress

Mute a finding for a time window without permanently disabling its rule. Muted
findings are **not scored** and do not affect exit codes; they reappear when the
window expires.

This differs from `ignore.rules` in [configuration](../configuration.md), which
disables a rule permanently and globally. Suppression is a temporary acknowledgement
("I know about this; hide it for 24h").

```bash
redis-doctor suppress add <finding.id> [--for 24h] [--affected X] [--target URL] [--reason "..."]
redis-doctor suppress list [--all]
redis-doctor suppress rm <id>
```

Suppressions are stored in a small SQLite database (default
`~/.redis-doctor/suppressions.db`, set via `suppress.path`), so they apply to both
the CLI and the [web dashboard](../guides/gui.md) and survive restarts.

## add

```bash
# Mute a finding everywhere for 24h (the default window)
redis-doctor suppress add server.blocked_clients --reason "known BLPOP consumers"

# Mute for a week
redis-doctor suppress add memory.high_fragmentation --for 7d

# Scope to one key/prefix/address (only that affected item is muted)
redis-doctor suppress add bigkey.big_memory --affected user:profile:123 --for 48h

# Scope to a single instance (by its redacted target)
redis-doctor suppress add config.no_persistence --target redis://cache-1:6379/0
```

Durations: `30m`, `24h`, `7d`, `2w`, `3600s`.

Matching: a finding is muted when its `id` equals the suppression's, and (if set)
its `--affected` matches one of the finding's affected items and its `--target`
matches the report's redacted target.

## list

```bash
redis-doctor suppress list          # active only
redis-doctor suppress list --all    # include expired
```

## rm

```bash
redis-doctor suppress rm 3          # remove suppression #3 (id from `list`)
```

## In a run

Active suppressions are applied automatically on every `analyze` (unless
`suppress.enabled` is false). The terminal/JSON report lists muted findings
separately so they stay visible:

```text
Suppressed: 1 finding(s) muted (not scored): server.blocked_clients
```

In the web dashboard, each finding has a **mute 24h** button, and the
**Suppressions** tab lists and manages them.
