# Adding a module

A worked example: add a module `pubsub` that flags a high number of Pub/Sub
channels. The same five steps apply to any new detector.

## 1. (Optional) a model

If the data does not fit an existing model, add one under `models/`. For a simple
count you can skip this and return a dict or a small dataclass.

## 2. A collector

`redis_doctor/collectors/pubsub.py`:

```python
from .base import Collector

class PubSubCollector(Collector):
    name = "pubsub"

    def collect(self, ctx) -> dict:
        channels = ctx.redis.execute("PUBSUB", "CHANNELS") or []
        return {"channel_count": len(channels)}
```

First, make sure any command you use is allowed in `safety.py` — add it to
`ALLOWED_COMMANDS` if it is genuinely read-only. See [Safety](../safety.md).

## 3. An analyzer

`redis_doctor/analyzers/pubsub_rules.py`:

```python
from ..models.finding import Category, Finding, Severity
from .base import Analyzer

CHANNEL_WARNING = 1000

class PubSubAnalyzer(Analyzer):
    name = "pubsub"

    def analyze(self, ctx) -> list[Finding]:
        data = ctx.collected.get("pubsub")
        if data is None:
            return []
        if data["channel_count"] > CHANNEL_WARNING:
            return [Finding(
                id="pubsub.many_channels",
                severity=Severity.WARNING,
                category=Category.SERVER,   # or add a new Category
                title=f"{data['channel_count']} active Pub/Sub channels",
                explanation="A very high channel count can indicate a leak.",
                evidence={"channel_count": data["channel_count"]},
                suggested_checks=["redis-cli PUBSUB CHANNELS"],
                suggested_fixes=["Audit subscribers for leaked channels"],
            )]
        return []
```

If you introduce a brand-new category, add it to the `Category` enum in
`models/finding.py`.

## 4. Register it

In `pipeline.py`, import both and add a `ModuleSpec` to `_registry()`:

```python
ModuleSpec("pubsub", PubSubCollector(), PubSubAnalyzer()),
```

If your analyzer reuses another module's data (like the keyspace sample), pass
`None` for the collector and add an entry to `_DEPENDENCIES`.

## 5. Rule pack + docs + tests

- Add `pubsub.many_channels: { enabled: true }` to `rules/default.yml`.
- Document the ID in the [findings catalog](../findings-catalog.md).
- Add a unit test (synthetic `ctx.collected`) asserting the ID and severity, and —
  ideally — an integration check against a seeded real Redis. See
  [Testing](testing.md).

## Reinstall after adding files

The editable install caches the module list, so after adding new files run:

```bash
pip install -e ".[dev]"
```

Then `pytest -q` and `ruff check redis_doctor tests`.
