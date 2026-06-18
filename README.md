# redis-doctor

Diagnose the production health of a Redis deployment — memory, keys, TTLs, streams,
clients, slow commands, replication, persistence, Sentinel, and Cluster — and explain,
for every problem found: what is wrong, why it is risky, how bad it is, how to verify it,
and how to fix it.

`redis-doctor` is **read-only by default**. It never runs a command that writes, deletes,
mutates config, or kills clients. `KEYS` and `MONITOR` are blocked unconditionally.

```bash
redis-doctor analyze redis://localhost:6379
```

## Documentation

Full documentation lives in [`docs/`](docs/). Read the Markdown source starting at
[`docs/md/index.md`](docs/md/index.md), or build the browsable HTML site:

```bash
python docs/tools/converter.py     # builds docs/html/ ; open docs/html/index.html
```

See `redis-doctor.md` for the full engineering specification.

## Install

```bash
pipx install redis-doctor
```

## Usage

```bash
redis-doctor analyze redis://localhost:6379
redis-doctor analyze redis://localhost:6379 --format json
redis-doctor scan-keys redis://localhost:6379
redis-doctor config-check redis://localhost:6379
redis-doctor inspect-stream redis://localhost:6379 my:stream
redis-doctor inspect-clients redis://localhost:6379
redis-doctor analyze redis://localhost:6379 --format markdown --output report.md
redis-doctor report report.json --format markdown
redis-doctor analyze-sentinel --sentinel-node host:26379 --master-name mymaster
redis-doctor analyze-cluster redis://localhost:7000
redis-doctor diff before.json after.json
redis-doctor analyze --fleet fleet.yml --output fleet.json
```

## Optional extras

```bash
pip install 'redis-doctor[tui]'   # interactive terminal UI (Textual)
pip install 'redis-doctor[gui]'   # web dashboard + PDF export (FastAPI, WeasyPrint)
```

```bash
redis-doctor tui redis://localhost:6379      # interactive TUI
redis-doctor serve --host 127.0.0.1 --port 8787   # local web dashboard + JSON API
```

The web GUI binds to localhost by default; no data leaves the machine. Passwords
entered in the UI are used only for the request and never persisted (history stores
only the redacted target).

## Configuration

Resolution order: built-in defaults < config file < environment < CLI flags.
See `redis-doctor.example.yml` for the full schema. Pass a file with `--config`.
Environment: `REDIS_DOCTOR_PASSWORD`, `REDIS_DOCTOR_USERNAME`, `REDIS_DOCTOR_CONFIG`.

## Exit codes

```
0  success; no findings at or above --fail-on
1  findings at/above the warning threshold
2  findings at/above the critical threshold
3  connection / authentication error
4  invalid config / arguments
5  internal error
```

`--fail-on none|warning|critical` (default none); `--no-fail` forces exit 0.

## Docker

```bash
docker build -t redis-doctor .
docker run --rm redis-doctor analyze redis://host.docker.internal:6379
```

## Standalone binary

```bash
pip install pyinstaller
pyinstaller redis-doctor.spec       # produces dist/redis-doctor
```

## CI integration

GitHub Actions:

```yaml
- name: Redis health gate
  run: |
    pipx install redis-doctor
    redis-doctor analyze "$REDIS_URL" --fail-on critical
```

GitLab CI:

```yaml
redis-health:
  image: python:3.11-slim
  script:
    - pip install redis-doctor
    - redis-doctor analyze "$REDIS_URL" --fail-on critical
```

Kubernetes CronJob:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: redis-doctor
spec:
  schedule: "0 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: redis-doctor
              image: redis-doctor:latest
              args: ["analyze", "redis://my-redis:6379", "--fail-on", "critical"]
```
