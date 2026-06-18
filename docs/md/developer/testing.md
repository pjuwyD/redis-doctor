# Testing

```bash
pip install -e ".[dev,tui,gui]"
pytest -q
ruff check redis_doctor tests
ruff format --check redis_doctor tests
```

## Layout

- `tests/unit/` — fast tests using **fakeredis** and synthetic data.
- `tests/integration/` — tests that need a real Redis (skipped gracefully when
  none is reachable).
- `tests/conftest.py` — fixtures: `fake_redis`, `safe_fake` (a `SafeRedis` over
  fakeredis), and `real_redis_url` (skips if `REDIS_DOCTOR_TEST_URL`, default
  `redis://redis:6379`, is unreachable).

## How analyzers are tested

Build a `RunContext`, drop synthetic data into `ctx.collected`, call the analyzer,
and assert on finding IDs and severities:

```python
def test_locks_without_ttl(safe_fake):
    from redis_doctor.pipeline import RunContext
    ctx = RunContext(redis=safe_fake, config=Config())
    ctx.collected["keyspace"] = _keyspace(
        [KeyInfo(key=f"lock:{i}", type="string", ttl_seconds=-1) for i in range(20)]
    )
    ids = {f.id: f for f in TTLAnalyzer().analyze(ctx)}
    assert ids["ttl.locks_without_ttl"].severity == Severity.CRITICAL
```

This mirrors the spec's seeded-state approach: for each known-bad state, assert the
exact finding IDs at the right severity, and that unrelated findings are absent.

## What the suite guarantees

- **Finding-ID assertions** for every analyzer.
- **Safety**: `KEYS`/`MONITOR` blocked, write commands blocked, `SafeRedis.pipe`
  guarded.
- **Output contract**: JSON validates against the `Report` model; exit codes match
  the [contract](../output-and-exit-codes.md#exit-codes) for each `--fail-on`;
  secrets never appear in any output.
- **TUI**: mounts headlessly (Textual pilot), panels render, key bindings work.
- **GUI**: API endpoints via FastAPI `TestClient`; PDF renders a real `%PDF`.

## Coverage gate

Core modules — `pipeline`, `scoring`, `rule_engine`, `connection`, `safety`, and
every analyzer — are held at **≥85%**. Check it:

```bash
pytest -q --cov=redis_doctor --cov-report=term-missing
```

## Verifying against a real Redis

Seed a known-bad local instance and run the CLI to confirm behavior end-to-end:

```bash
redis-server --port 7799 --maxmemory 4mb --maxmemory-policy noeviction --save '' \
  --daemonize yes --logfile /tmp/r.log
redis-cli -p 7799 mset lock:1 1 lock:2 1            # locks without TTL
redis-doctor analyze redis://localhost:7799
redis-cli -p 7799 shutdown nosave
```
