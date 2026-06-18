"""Stream diagnostics analyzer (Section 9.7)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.finding import Category, Finding, Severity
from .base import Analyzer

if TYPE_CHECKING:
    from ..pipeline import RunContext

LAG_WARNING = 1000
MANY_INACTIVE = 5


def _hms(ms: int) -> str:
    s = ms // 1000
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"


class StreamAnalyzer(Analyzer):
    name = "streams"

    def analyze(self, ctx: RunContext) -> list[Finding]:
        streams = ctx.collected.get("streams")
        if not streams:
            return []

        th = ctx.config.thresholds
        idle_ms_limit = th.consumer_idle_warning_seconds * 1000
        findings: list[Finding] = []

        for st in streams:
            if st.length > th.stream_length_warning:
                findings.append(
                    Finding(
                        id="streams.length_high",
                        severity=Severity.CRITICAL,
                        category=Category.STREAMS,
                        title=f"Stream {st.name} has {st.length:,} entries",
                        explanation=(
                            "A very long stream consumes memory and slows range reads; "
                            "without trimming it grows unbounded."
                        ),
                        evidence={"stream": st.name, "length": st.length},
                        suggested_checks=[f"redis-cli XLEN {st.name}"],
                        suggested_fixes=[
                            "Trim with XTRIM MAXLEN or MINID",
                            "Add a retention policy",
                        ],
                        affected=[st.name],
                    )
                )

            if not st.groups:
                findings.append(
                    Finding(
                        id="streams.no_groups",
                        severity=Severity.WARNING,
                        category=Category.STREAMS,
                        title=f"Stream {st.name} has no consumer groups",
                        explanation=(
                            "A stream with no consumer groups may indicate entries are "
                            "being produced but never consumed."
                        ),
                        evidence={"stream": st.name, "length": st.length},
                        suggested_checks=[f"redis-cli XINFO GROUPS {st.name}"],
                        suggested_fixes=["Create a consumer group or confirm this is intended"],
                        affected=[st.name],
                    )
                )

            for g in st.groups:
                self._group_findings(findings, th, idle_ms_limit, st, g)

        return findings

    def _group_findings(self, findings, th, idle_ms_limit, st, g) -> None:
        if g.pending > th.stream_pending_warning:
            findings.append(
                Finding(
                    id="streams.pending_high",
                    severity=Severity.CRITICAL,
                    category=Category.STREAMS,
                    title=f"Group {g.name} on {st.name} has {g.pending:,} pending messages",
                    explanation=(
                        "A large pending-entries list means consumers are not "
                        "acknowledging messages fast enough; work is backing up."
                    ),
                    evidence={"stream": st.name, "group": g.name, "pending": g.pending},
                    suggested_checks=[
                        f"redis-cli XINFO GROUPS {st.name}",
                        f"redis-cli XPENDING {st.name} {g.name}",
                    ],
                    suggested_fixes=[
                        "Scale up consumers",
                        "Reclaim stuck messages with XAUTOCLAIM",
                    ],
                    affected=[st.name],
                )
            )

        if g.consumers == 0 and (g.pending > 0 or st.length > 0):
            findings.append(
                Finding(
                    id="streams.no_consumers",
                    severity=Severity.CRITICAL,
                    category=Category.STREAMS,
                    title=f"Group {g.name} on {st.name} has zero consumers",
                    explanation=(
                        "A group with no consumers is not processing messages; the "
                        "pending list will only grow."
                    ),
                    evidence={"stream": st.name, "group": g.name, "pending": g.pending},
                    suggested_checks=[f"redis-cli XINFO CONSUMERS {st.name} {g.name}"],
                    suggested_fixes=["Start consumers for this group"],
                    affected=[st.name],
                )
            )

        if g.lag is not None and g.lag >= LAG_WARNING:
            findings.append(
                Finding(
                    id="streams.lag_high",
                    severity=Severity.WARNING,
                    category=Category.STREAMS,
                    title=f"Group {g.name} on {st.name} is {g.lag:,} entries behind",
                    explanation="The group's last-delivered id is far behind the stream tail.",
                    evidence={"stream": st.name, "group": g.name, "lag": g.lag},
                    suggested_checks=[f"redis-cli XINFO GROUPS {st.name}"],
                    suggested_fixes=["Increase consumer throughput"],
                    affected=[st.name],
                )
            )

        idle_with_pending = [
            c for c in g.consumer_list if c.idle_ms >= idle_ms_limit and c.pending > 0
        ]
        for c in idle_with_pending:
            findings.append(
                Finding(
                    id="streams.idle_consumer_with_pending",
                    severity=Severity.CRITICAL,
                    category=Category.STREAMS,
                    title=(
                        f"Consumer {c.name} ({g.name}@{st.name}) has {c.pending:,} pending, "
                        f"idle {_hms(c.idle_ms)}"
                    ),
                    explanation=(
                        "A consumer holding pending messages while idle has likely died; "
                        "its messages are stuck until reclaimed."
                    ),
                    evidence={
                        "stream": st.name,
                        "group": g.name,
                        "consumer": c.name,
                        "pending": c.pending,
                        "idle_ms": c.idle_ms,
                    },
                    suggested_checks=[f"redis-cli XINFO CONSUMERS {st.name} {g.name}"],
                    suggested_fixes=[
                        "Reclaim with XAUTOCLAIM",
                        "Remove the dead consumer with XGROUP DELCONSUMER",
                    ],
                    affected=[st.name],
                )
            )

        inactive = [c for c in g.consumer_list if c.idle_ms >= idle_ms_limit]
        if len(inactive) >= MANY_INACTIVE:
            findings.append(
                Finding(
                    id="streams.many_inactive_consumers",
                    severity=Severity.WARNING,
                    category=Category.STREAMS,
                    title=f"Group {g.name} on {st.name} has {len(inactive)} idle consumers",
                    explanation="Many idle consumers suggest leaked or orphaned workers.",
                    evidence={"stream": st.name, "group": g.name, "idle_consumers": len(inactive)},
                    suggested_checks=[f"redis-cli XINFO CONSUMERS {st.name} {g.name}"],
                    suggested_fixes=["Clean up idle consumers with XGROUP DELCONSUMER"],
                    affected=[st.name],
                )
            )
