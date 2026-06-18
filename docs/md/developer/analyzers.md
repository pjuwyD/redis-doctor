# Analyzers

An **analyzer** turns collected data into [`Finding`](architecture.md#data-model)
objects. It reads from `ctx.collected` and never touches Redis directly.

## The contract

```python
from redis_doctor.analyzers.base import Analyzer
from redis_doctor.models.finding import Category, Finding, Severity

class MyAnalyzer(Analyzer):
    name = "mymodule"

    def analyze(self, ctx) -> list[Finding]:
        data = ctx.collected.get("mymodule")
        if data is None:          # collector was skipped — degrade quietly
            return []
        th = ctx.config.thresholds
        findings: list[Finding] = []
        if data.some_metric > th.some_threshold:
            findings.append(Finding(
                id="mymodule.some_problem",
                severity=Severity.WARNING,
                category=Category.MEMORY,
                title="One-line human summary",
                explanation="Why this is risky, in plain language.",
                evidence={"some_metric": data.some_metric},
                suggested_checks=["redis-cli ..."],
                suggested_fixes=["Concrete remediation (never auto-applied)"],
                affected=["optional key/prefix/addr names"],
            ))
        return findings
```

## Rules to follow

- **Return `[]` when your input is missing.** If `ctx.collected.get(name)` is
  `None`, the collector was skipped — do not raise.
- **Use stable IDs from the [catalog](../findings-catalog.md).** Tests assert on
  them; they are a contract.
- **Read thresholds from config, do not hardcode.** Global thresholds live in
  `ctx.config.thresholds`. For per-rule overrides, ask the rule engine:
  `ctx.rules.get("mymodule.some_problem").get("warning_pct", default)` — see
  [Rule engine](rule-engine.md).
- **Make `evidence` machine-readable** (the numbers that triggered the finding).
  Put the human story in `explanation`.
- **`affected` holds user data** (key names, prefixes, client addresses). The
  renderers treat these as plain text so they are never interpreted as markup.
- **Enable/ignore is not your concern.** The pipeline filters emitted findings
  through `RuleEngine.is_active(id)`. Just emit; the engine decides.

## Severity

Pick severity by impact, and let thresholds decide the boundary:

- **critical** — imminent data loss, write rejection, or outage (e.g.
  `memory.high_usage_noeviction`, `ttl.locks_without_ttl`, `persistence.rdb_failed`).
- **warning** — a real risk that is not yet an outage.
- **info** — context worth noting, no score penalty.

## Registration

Add your analyzer to `_registry()` in `pipeline.py`, paired with its collector
(or `None` if it reuses another module's data). See
[Adding a module](adding-a-module.md).

## Standalone analyzers

Sentinel and Cluster analyzers are plain functions (`analyze_sentinel(topo, cfg)`,
`analyze_cluster(data)`) rather than registry classes, because they run outside
the main pipeline. They still return `list[Finding]` and feed `build_report()`.
