"""Configuration risk analyzer (Section 9.11)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.finding import Category, Finding, Severity
from .base import Analyzer

if TYPE_CHECKING:
    from ..pipeline import RunContext

# A slowlog threshold above this many microseconds is effectively disabled.
SLOWLOG_ABSURD_US = 1_000_000
# tcp-keepalive considered "very high" above this many seconds.
KEEPALIVE_HIGH_SECONDS = 600


def _int(values: dict, key: str, default: int = 0) -> int:
    try:
        return int(values.get(key, default))
    except (ValueError, TypeError):
        return default


class ConfigAnalyzer(Analyzer):
    name = "config"

    def analyze(self, ctx: RunContext) -> list[Finding]:
        values = ctx.collected.get("config_values")
        if values is None:
            return []

        th = ctx.config.thresholds
        findings: list[Finding] = []

        maxmemory = _int(values, "maxmemory")
        policy = values.get("maxmemory-policy", "noeviction")
        timeout = _int(values, "timeout")
        keepalive = _int(values, "tcp-keepalive")
        slowlog_threshold = _int(values, "slowlog-log-slower-than", -1)

        if maxmemory == 0:
            findings.append(
                Finding(
                    id="config.no_maxmemory",
                    severity=Severity.WARNING,
                    category=Category.CONFIG,
                    title="maxmemory is not set",
                    explanation=(
                        "Without maxmemory, Redis is unbounded and can exhaust host memory."
                    ),
                    evidence={"maxmemory": 0},
                    suggested_checks=["redis-cli CONFIG GET maxmemory"],
                    suggested_fixes=["Set maxmemory and an eviction policy"],
                )
            )
        elif policy == "noeviction":
            findings.append(
                Finding(
                    id="config.risky_eviction_policy",
                    severity=Severity.WARNING,
                    category=Category.CONFIG,
                    title="maxmemory-policy is noeviction with a memory limit set",
                    explanation=(
                        "With noeviction, Redis rejects writes when maxmemory is "
                        "reached. For a cache, an LRU/LFU policy is usually safer."
                    ),
                    evidence={"maxmemory_policy": policy, "maxmemory": maxmemory},
                    suggested_checks=["redis-cli CONFIG GET maxmemory-policy"],
                    suggested_fixes=[
                        "Use allkeys-lru/allkeys-lfu for a cache workload",
                        "Keep noeviction only if data loss is unacceptable",
                    ],
                )
            )

        if timeout == 0:
            idle_count = self._idle_client_count(ctx, th.idle_client_warning_seconds)
            if idle_count >= th.idle_client_warning_count:
                findings.append(
                    Finding(
                        id="config.timeout_zero_with_idle",
                        severity=Severity.WARNING,
                        category=Category.CONFIG,
                        title="timeout=0 while many idle clients are connected",
                        explanation=(
                            "With timeout=0, Redis never closes idle connections. "
                            "Combined with many idle clients, this leaks connections "
                            "and file descriptors."
                        ),
                        evidence={
                            "timeout": 0,
                            "idle_clients": idle_count,
                            "idle_threshold_seconds": th.idle_client_warning_seconds,
                        },
                        suggested_checks=[
                            "redis-cli CONFIG GET timeout",
                            "redis-cli CLIENT LIST",
                        ],
                        suggested_fixes=[
                            "Set a non-zero timeout",
                            "Fix clients that leak idle connections",
                        ],
                    )
                )

        if keepalive == 0 or keepalive > KEEPALIVE_HIGH_SECONDS:
            findings.append(
                Finding(
                    id="config.tcp_keepalive_bad",
                    severity=Severity.INFO,
                    category=Category.CONFIG,
                    title=f"tcp-keepalive is {'disabled' if keepalive == 0 else 'very high'}",
                    explanation=(
                        "Disabled or very high TCP keepalive lets dead connections "
                        "linger, holding resources until detected."
                    ),
                    evidence={"tcp_keepalive": keepalive},
                    suggested_checks=["redis-cli CONFIG GET tcp-keepalive"],
                    suggested_fixes=["Set tcp-keepalive to ~300 seconds"],
                )
            )

        # "no persistence enabled" is reported once, by the persistence module
        # (persistence.none_enabled), to avoid a duplicate finding.

        if slowlog_threshold < 0 or slowlog_threshold >= SLOWLOG_ABSURD_US:
            findings.append(
                Finding(
                    id="config.slowlog_disabled",
                    severity=Severity.WARNING,
                    category=Category.CONFIG,
                    title="slowlog is effectively disabled",
                    explanation=(
                        "A negative or extremely high slowlog-log-slower-than means "
                        "slow commands are not recorded, hiding performance problems."
                    ),
                    evidence={"slowlog_log_slower_than": slowlog_threshold},
                    suggested_checks=["redis-cli CONFIG GET slowlog-log-slower-than"],
                    suggested_fixes=["Set slowlog-log-slower-than to e.g. 10000 (10ms)"],
                )
            )

        return findings

    def _idle_client_count(self, ctx: RunContext, idle_seconds: int) -> int:
        clients = ctx.collected.get("clients")
        if clients is None:
            try:
                from ..collectors.clients import fetch_clients

                clients = fetch_clients(ctx.redis)
            except Exception:
                return 0
        return sum(1 for c in clients if c.idle_seconds >= idle_seconds)
