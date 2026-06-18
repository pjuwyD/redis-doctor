"""Rule engine (Section 10.1).

Loads the shipped default rule pack, applies user `rules:` overrides per rule ID,
and `ignore.rules` disabling. Analyzers ask `get(rule_id)` for thresholds; the
pipeline asks `is_active(rule_id)` before emitting a finding.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import Config


def _default_pack_path() -> Path | None:
    # Packaged location (wheel) then dev/repo location.
    candidates = [
        Path(__file__).parent / "rules" / "default.yml",
        Path(__file__).parent.parent / "rules" / "default.yml",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _load_default_rules() -> dict[str, dict[str, Any]]:
    path = _default_pack_path()
    if path is None:
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return data.get("rules", {}) or {}


class RuleConfig:
    """Resolved configuration for one rule ID."""

    def __init__(self, rule_id: str, data: dict[str, Any]):
        self.id = rule_id
        self.enabled: bool = bool(data.get("enabled", True))
        self.params: dict[str, Any] = {k: v for k, v in data.items() if k != "enabled"}

    def get(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)


class RuleEngine:
    def __init__(self, rules: dict[str, dict[str, Any]], ignored: set[str]):
        self._rules = rules
        self._ignored = ignored

    @classmethod
    def from_config(cls, config: Config) -> RuleEngine:
        merged = _load_default_rules()
        for rule_id, override in (config.rules or {}).items():
            base = dict(merged.get(rule_id, {}))
            base.update(override or {})
            merged[rule_id] = base
        return cls(merged, set(config.ignore.rules))

    def get(self, rule_id: str) -> RuleConfig:
        return RuleConfig(rule_id, self._rules.get(rule_id, {}))

    def is_active(self, rule_id: str) -> bool:
        if rule_id in self._ignored:
            return False
        return self.get(rule_id).enabled
