# Configuration

Redis Doctor reads settings from, in increasing order of precedence:

1. **Built-in defaults**
2. **A config file** (`--config redis-doctor.yml` or `REDIS_DOCTOR_CONFIG`)
3. **Environment variables**
4. **CLI flags**

A flag always wins over the file; the file always wins over the defaults.

## Environment variables

| Variable | Purpose |
|---|---|
| `REDIS_DOCTOR_PASSWORD` | password used if `--password` is not given |
| `REDIS_DOCTOR_USERNAME` | username used if `--username` is not given |
| `REDIS_DOCTOR_CONFIG` | path to a config file if `--config` is not given |

SMTP settings for the email notifier are also read from the environment:
`REDIS_DOCTOR_SMTP_HOST`, `REDIS_DOCTOR_SMTP_PORT`, `REDIS_DOCTOR_SMTP_FROM`.

## Full config file schema

```yaml
connection:
  timeout_seconds: 5

scan:
  sample_size: 10000        # max keys to sample
  count: 1000               # COUNT hint per SCAN iteration
  max_seconds: 30           # hard cap on total scan time
  prefix_depth: 2           # tokens kept when grouping prefixes
  prefix_separators: ":.|/_" # characters that split a key into tokens

thresholds:
  memory_warning_pct: 80
  memory_critical_pct: 90
  fragmentation_warning_ratio: 1.5
  idle_client_warning_seconds: 3600
  idle_client_warning_count: 100
  idle_client_critical_count: 500
  blocked_client_warning: 1
  big_key_mb: 10
  huge_key_mb: 100
  large_collection: 10000
  huge_collection: 100000
  stream_length_warning: 100000
  stream_pending_warning: 10000
  consumer_idle_warning_seconds: 3600
  slowlog_max_entries: 128
  replica_lag_warning_seconds: 30
  replica_lag_critical_seconds: 120

ttl_expectations:
  - pattern: "session:*"
    ttl_required: true
    max_ttl_seconds: 86400
  - pattern: "lock:*"
    ttl_required: true
    max_ttl_seconds: 300
  - pattern: "cache:*"
    ttl_required: true

rules:                      # per-rule overrides / disabling
  memory.high_usage:
    enabled: true
    warning_pct: 80
    critical_pct: 90
  clients.idle_many:
    enabled: true
    idle_seconds: 3600
    warning_count: 100
    critical_count: 500

ignore:
  keys:
    - "metrics:*"           # excluded from sampling/analysis
  rules:
    - "security.default_user"  # this finding is never emitted

output:
  format: terminal          # terminal | markdown | json
  fail_on: none             # none | warning | critical

notify:
  slack_webhook_url: null
  email: null

history:
  enabled: false
  path: "~/.redis-doctor/history.db"

suppress:
  enabled: true
  path: "~/.redis-doctor/suppressions.db"
```

## Suppressions vs. ignore

`ignore.rules` disables a rule **permanently and globally**. A **suppression**
(see [`suppress`](commands/suppress.md)) mutes a finding **temporarily** (and
optionally scoped to one affected item or target), then it reappears. Suppressed
findings are excluded from the score and exit code but reported separately. Set
`suppress.enabled: false` to ignore the store entirely.

A ready-to-edit copy ships as `redis-doctor.example.yml`.

## Scan / sampling

The keyspace is **never fully scanned by default**. Sampling stops as soon as any
limit is hit (`sample_size` reached or `max_seconds` elapsed). The report always
states how many keys were scanned, the estimated total, and a confidence level.
See the [keyspace sampler internals](developer/collectors.md#keyspace-sampler).

These can also be set per-run as flags on `analyze` and `scan-keys`:
`--sample-size`, `--scan-count`, `--max-scan-seconds`, `--prefix-depth`,
`--prefix-separators`.

## Thresholds

Every analyzer reads its thresholds from configuration rather than hardcoding
them. The `thresholds:` block sets global defaults; a `rules:` entry can override
specific values for one finding ID (see below).

## TTL expectations

`ttl_expectations` lets you encode your conventions. A pattern with
`ttl_required: true` whose matching keys lack a TTL produces a finding; a
`max_ttl_seconds` that is exceeded produces `ttl.excessive_ttl`. Patterns use glob
syntax (`session:*`).

## Rules: enable, disable, override

The shipped rule pack (`rules/default.yml`) lists every finding ID with its
default `enabled` state and thresholds. Your `rules:` block overrides any field
per rule ID. To turn a rule off:

```yaml
rules:
  server.recent_restart:
    enabled: false
```

To raise a threshold for one rule only:

```yaml
rules:
  memory.high_usage:
    warning_pct: 70
    critical_pct: 85
```

A finding is emitted only if its rule is enabled **and** its ID is not in
`ignore.rules`. See the [rule engine](developer/rule-engine.md).

## Ignore

```yaml
ignore:
  keys:                     # glob patterns excluded from the keyspace sample
    - "metrics:*"
  rules:                    # finding IDs that are never emitted
    - "security.default_user"
```

## Output and CI

`output.format` sets the default rendering and `output.fail_on` the default
CI-gate behavior; both are overridden by `--format` and `--fail-on`. See
[Output & exit codes](output-and-exit-codes.md).
