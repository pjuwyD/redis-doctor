"""Memory analyzer (Section 9.2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.finding import Category, Confidence, Finding, Severity
from .base import Analyzer

if TYPE_CHECKING:
    from ..pipeline import RunContext

NOEVICTION_USAGE_PCT = 85.0
RSS_OVERHEAD_RATIO = 1.5
RSS_OVERHEAD_MIN_BYTES = 100 * 1024 * 1024


class MemoryAnalyzer(Analyzer):
    name = "memory"

    def analyze(self, ctx: RunContext) -> list[Finding]:
        stats = ctx.collected.get("memory")
        if stats is None:
            return []

        th = ctx.config.thresholds
        # Per-rule overrides from the rule engine take precedence over globals.
        rule = ctx.rules.get("memory.high_usage") if ctx.rules else None
        warning_pct = (
            rule.get("warning_pct", th.memory_warning_pct) if rule else th.memory_warning_pct
        )
        critical_pct = (
            rule.get("critical_pct", th.memory_critical_pct) if rule else th.memory_critical_pct
        )
        findings: list[Finding] = []
        used = stats.used_memory
        maxmem = stats.maxmemory
        policy = stats.maxmemory_policy
        pct = (100 * used / maxmem) if maxmem else None

        if maxmem == 0:
            findings.append(
                Finding(
                    id="memory.no_maxmemory",
                    severity=Severity.WARNING,
                    category=Category.MEMORY,
                    title="maxmemory is unset (memory is unbounded)",
                    explanation=(
                        "Without a maxmemory limit, Redis can consume all system "
                        "memory and be killed by the OOM killer."
                    ),
                    evidence={"maxmemory": 0, "used_memory": used},
                    suggested_checks=["redis-cli CONFIG GET maxmemory"],
                    suggested_fixes=[
                        "Set a maxmemory limit appropriate for the host",
                        "Choose an eviction policy suited to the workload",
                    ],
                )
            )

        if pct is not None:
            if pct >= critical_pct:
                findings.append(self._high_usage(Severity.CRITICAL, pct, used, maxmem, policy))
            elif pct >= warning_pct:
                findings.append(self._high_usage(Severity.WARNING, pct, used, maxmem, policy))

            if policy == "noeviction" and pct >= NOEVICTION_USAGE_PCT:
                findings.append(
                    Finding(
                        id="memory.high_usage_noeviction",
                        severity=Severity.CRITICAL,
                        category=Category.MEMORY,
                        title="Redis memory usage is high with noeviction policy",
                        explanation=(
                            "With noeviction, Redis rejects writes once maxmemory is "
                            "reached. At this usage level, writes are about to fail."
                        ),
                        evidence={
                            "used_memory_pct": round(pct, 1),
                            "maxmemory_policy": policy,
                            "used_memory": used,
                            "maxmemory": maxmem,
                        },
                        suggested_checks=[
                            "redis-cli INFO memory",
                            "redis-cli CONFIG GET maxmemory-policy",
                        ],
                        suggested_fixes=[
                            "Increase maxmemory",
                            "Remove unneeded keys / add TTLs",
                            "Use a cache eviction policy (e.g. allkeys-lru)",
                        ],
                    )
                )

        if stats.mem_fragmentation_ratio > th.fragmentation_warning_ratio:
            findings.append(
                Finding(
                    id="memory.high_fragmentation",
                    severity=Severity.WARNING,
                    category=Category.MEMORY,
                    title=(
                        f"Memory fragmentation ratio is high ({stats.mem_fragmentation_ratio:.2f})"
                    ),
                    explanation=(
                        "A high fragmentation ratio means the allocator holds much "
                        "more RSS than the data needs, wasting physical memory."
                    ),
                    evidence={"mem_fragmentation_ratio": stats.mem_fragmentation_ratio},
                    suggested_checks=["redis-cli INFO memory | grep fragmentation"],
                    suggested_fixes=[
                        "Consider activedefrag yes",
                        "Restart during a maintenance window to reclaim RSS",
                    ],
                )
            )

        if (
            used > 0
            and stats.used_memory_rss > RSS_OVERHEAD_RATIO * used
            and (stats.used_memory_rss - used) > RSS_OVERHEAD_MIN_BYTES
        ):
            findings.append(
                Finding(
                    id="memory.rss_overhead",
                    severity=Severity.WARNING,
                    category=Category.MEMORY,
                    confidence=Confidence.MEDIUM,
                    title="Resident memory (RSS) is much larger than used memory",
                    explanation=(
                        "Large RSS overhead indicates allocator fragmentation or "
                        "copy-on-write from forks holding extra physical memory."
                    ),
                    evidence={
                        "used_memory": used,
                        "used_memory_rss": stats.used_memory_rss,
                    },
                    suggested_checks=["redis-cli INFO memory"],
                    suggested_fixes=["Investigate fragmentation / fork overhead"],
                )
            )

        return findings

    def _high_usage(self, severity, pct, used, maxmem, policy) -> Finding:
        return Finding(
            id="memory.high_usage",
            severity=severity,
            category=Category.MEMORY,
            title=f"Redis memory usage is high ({pct:.0f}% of maxmemory)",
            explanation=(
                "High memory usage risks evictions or rejected writes depending on "
                "the eviction policy."
            ),
            evidence={
                "used_memory_pct": round(pct, 1),
                "used_memory": used,
                "maxmemory": maxmem,
                "maxmemory_policy": policy,
            },
            suggested_checks=["redis-cli INFO memory"],
            suggested_fixes=["Increase maxmemory", "Reduce data footprint", "Add TTLs"],
        )
