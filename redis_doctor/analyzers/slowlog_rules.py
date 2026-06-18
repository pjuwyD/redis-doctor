"""Slowlog analyzer (Section 9.9)."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from ..models.finding import Category, Finding, Severity
from .base import Analyzer

if TYPE_CHECKING:
    from ..pipeline import RunContext

# Commands that are O(N) and dangerous on large data sets.
_DANGEROUS = {"KEYS", "SORT", "SMEMBERS", "HGETALL", "LRANGE", "FLUSHALL", "FLUSHDB"}
REPEAT_THRESHOLD = 5
NEAR_MAX_SHARE = 0.9


def _pattern(entry) -> str:
    # LRANGE key 0 -1 -> "LRANGE 0 -1"; otherwise just the command name.
    if entry.command == "LRANGE" and entry.args[-2:] == ["0", "-1"]:
        return "LRANGE 0 -1"
    return entry.command


class SlowlogAnalyzer(Analyzer):
    name = "slowlog"

    def analyze(self, ctx: RunContext) -> list[Finding]:
        data = ctx.collected.get("slowlog")
        if not data:
            return []

        entries = data.get("entries", [])
        length = data.get("length", 0)
        if not entries:
            return []

        findings: list[Finding] = []

        dangerous = [e for e in entries if e.command in _DANGEROUS]
        if dangerous:
            names = sorted({e.command for e in dangerous})
            findings.append(
                Finding(
                    id="slowlog.dangerous_command",
                    severity=Severity.CRITICAL,
                    category=Category.SLOWLOG,
                    title=f"Dangerous O(N) commands in slowlog: {', '.join(names)}",
                    explanation=(
                        "Commands like KEYS, SORT, SMEMBERS, HGETALL and full LRANGE "
                        "scan large data sets and block the server."
                    ),
                    evidence={
                        "commands": names,
                        "occurrences": len(dangerous),
                        "max_duration_us": max(e.duration_us for e in dangerous),
                    },
                    suggested_checks=["redis-cli SLOWLOG GET 10"],
                    suggested_fixes=[
                        "Replace KEYS with SCAN",
                        "Avoid full-collection reads on hot paths",
                    ],
                    affected=names,
                )
            )

        counts = Counter(_pattern(e) for e in entries)
        repeated = [(pat, n) for pat, n in counts.items() if n >= REPEAT_THRESHOLD]
        if repeated:
            repeated.sort(key=lambda x: x[1], reverse=True)
            top = repeated[0]
            findings.append(
                Finding(
                    id="slowlog.repeated_slow_command",
                    severity=Severity.WARNING,
                    category=Category.SLOWLOG,
                    title=f"Slow command pattern '{top[0]}' repeats {top[1]}×",
                    explanation=(
                        "A repeatedly slow command pattern is a systemic performance "
                        "problem rather than a one-off."
                    ),
                    evidence={"patterns": dict(repeated)},
                    suggested_checks=["redis-cli SLOWLOG GET 25"],
                    suggested_fixes=["Optimize or cache the offending command pattern"],
                    affected=[p for p, _ in repeated],
                )
            )

        values = ctx.collected.get("config_values") or {}
        try:
            max_len = int(values.get("slowlog-max-len", 128))
        except (ValueError, TypeError):
            max_len = 128
        if max_len > 0 and length >= NEAR_MAX_SHARE * max_len:
            findings.append(
                Finding(
                    id="slowlog.length_near_max",
                    severity=Severity.WARNING,
                    category=Category.SLOWLOG,
                    title=f"Slowlog is near its capacity ({length}/{max_len})",
                    explanation=(
                        "A full slowlog means older slow entries are being discarded, "
                        "so you may be missing slow commands."
                    ),
                    evidence={"length": length, "slowlog_max_len": max_len},
                    suggested_checks=["redis-cli SLOWLOG LEN"],
                    suggested_fixes=[
                        "Increase slowlog-max-len",
                        "Investigate why so many commands are slow",
                    ],
                )
            )

        return findings
