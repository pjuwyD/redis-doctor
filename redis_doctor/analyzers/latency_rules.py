"""Latency analyzer (Section 9.10).

Redis has no config-level latency threshold, so a sensible default spike
threshold is used here; the rule engine can override it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.finding import Category, Finding, Severity
from .base import Analyzer

if TYPE_CHECKING:
    from ..pipeline import RunContext

SPIKE_MS = 100
FORK_SLOW_MS = 100
AOF_FSYNC_SLOW_MS = 100


class LatencyAnalyzer(Analyzer):
    name = "latency"

    def analyze(self, ctx: RunContext) -> list[Finding]:
        data = ctx.collected.get("latency")
        if data is None or not data.events:
            return []

        findings: list[Finding] = []
        by_event = {e["event"]: e for e in data.events}

        spiking = [e for e in data.events if e["max_ms"] >= SPIKE_MS]
        # fork / aof-fsync get dedicated findings; keep them out of the generic spike.
        generic = [e for e in spiking if e["event"] not in ("fork", "aof-fsync")]
        if generic:
            findings.append(
                Finding(
                    id="latency.spike",
                    severity=Severity.WARNING,
                    category=Category.LATENCY,
                    title=f"{len(generic)} latency event(s) exceeded {SPIKE_MS}ms",
                    explanation=(
                        "Latency spikes cause slow commands and tail-latency that "
                        "degrade application responsiveness."
                    ),
                    evidence={
                        "events": {e["event"]: e["max_ms"] for e in generic},
                        "threshold_ms": SPIKE_MS,
                    },
                    suggested_checks=["redis-cli LATENCY LATEST", "redis-cli LATENCY DOCTOR"],
                    suggested_fixes=["Run LATENCY DOCTOR for guidance"],
                    affected=[e["event"] for e in generic],
                )
            )

        fork = by_event.get("fork")
        if fork and fork["max_ms"] >= FORK_SLOW_MS:
            findings.append(
                Finding(
                    id="latency.fork_slow",
                    severity=Severity.WARNING,
                    category=Category.LATENCY,
                    title=f"fork latency is high ({fork['max_ms']}ms max)",
                    explanation=(
                        "Slow forks stall the server during RDB/AOF rewrites, "
                        "blocking all clients for the fork duration."
                    ),
                    evidence={"max_ms": fork["max_ms"]},
                    suggested_checks=["redis-cli LATENCY LATEST"],
                    suggested_fixes=[
                        "Reduce dataset size",
                        "Ensure transparent huge pages are disabled",
                    ],
                )
            )

        fsync = by_event.get("aof-fsync")
        if fsync and fsync["max_ms"] >= AOF_FSYNC_SLOW_MS:
            findings.append(
                Finding(
                    id="latency.aof_fsync_slow",
                    severity=Severity.WARNING,
                    category=Category.LATENCY,
                    title=f"aof-fsync latency is high ({fsync['max_ms']}ms max)",
                    explanation=(
                        "Slow AOF fsyncs delay writes and can stall the event loop "
                        "depending on the appendfsync policy."
                    ),
                    evidence={"max_ms": fsync["max_ms"]},
                    suggested_checks=["redis-cli LATENCY LATEST"],
                    suggested_fixes=["Check disk performance", "Review appendfsync policy"],
                )
            )

        return findings
