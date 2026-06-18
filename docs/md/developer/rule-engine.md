# Rule engine

`rule_engine.py` decouples detection logic from policy. Analyzers ask it for
thresholds and the pipeline asks it whether a finding may be emitted.

## The rule pack

`rules/default.yml` lists **every** finding ID with its default `enabled` state and
optional default thresholds:

```yaml
rules:
  memory.high_usage: { enabled: true, warning_pct: 80, critical_pct: 90 }
  server.recent_restart: { enabled: true }
  ...
```

The pack is bundled into the wheel (and the PyInstaller binary) at
`redis_doctor/rules/default.yml`; the engine also finds it in the source tree
during development.

## Resolution

`RuleEngine.from_config(config)` merges, per rule ID:

```text
default.yml  <  config "rules:" overrides
```

and records `config.ignore.rules`. It exposes:

- `get(rule_id) -> RuleConfig` — `.enabled` plus a `params` dict
  (`rule.get("warning_pct", default)`).
- `is_active(rule_id) -> bool` — `enabled` **and** not in `ignore.rules`.

## How emission is gated

The pipeline filters every analyzer's output:

```python
findings = [f for f in findings if engine.is_active(f.id)]
```

So an analyzer always emits; the engine decides what survives. Disabling a rule
(`rules.<id>.enabled: false`) and ignoring it (`ignore.rules: [<id>]`) both remove
it — see [Configuration](../configuration.md#rules-enable-disable-override).

## Per-rule threshold overrides

An analyzer that wants a per-rule override reads it from the engine, falling back
to the global threshold:

```python
rule = ctx.rules.get("memory.high_usage")
warning_pct = rule.get("warning_pct", ctx.config.thresholds.memory_warning_pct)
```

Today `memory.high_usage` demonstrates this; most analyzers use the global
`thresholds:` block, which is sufficient for the majority of tuning. Wiring more
per-rule overrides is a safe, mechanical change if you need them.

## Adding a new rule

1. Emit the finding from an analyzer with a new `category.name` ID.
2. Add the ID to `rules/default.yml` with `{ enabled: true }` (and any default
   threshold params).
3. Document it in the [findings catalog](../findings-catalog.md).
4. Add a test asserting the ID and severity.
