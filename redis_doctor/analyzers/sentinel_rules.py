"""Sentinel analyzer (Section 9.15). Operates on a SentinelTopology."""

from __future__ import annotations

from ..collectors.sentinel import SentinelTopology
from ..config import Config
from ..models.finding import Category, Finding, Severity

FAILOVER_TIMEOUT_UNUSUAL_MS = 60_000


def analyze_sentinel(topo: SentinelTopology, config: Config) -> list[Finding]:
    th = config.thresholds
    findings: list[Finding] = []

    if topo.quorum and topo.reachable_sentinels < topo.quorum:
        findings.append(
            Finding(
                id="sentinel.insufficient_quorum",
                severity=Severity.CRITICAL,
                category=Category.SENTINEL,
                title=(
                    f"Only {topo.reachable_sentinels} Sentinel(s) reachable, "
                    f"but quorum is {topo.quorum}"
                ),
                explanation=(
                    "If fewer Sentinels than the quorum are reachable, automatic "
                    "failover cannot happen and the cluster cannot self-heal."
                ),
                evidence={
                    "reachable_sentinels": topo.reachable_sentinels,
                    "quorum": topo.quorum,
                },
                suggested_checks=["redis-cli -p <sentinel> SENTINEL master <name>"],
                suggested_fixes=["Restore unreachable Sentinels", "Review the quorum setting"],
            )
        )

    if len(topo.master_addrs) > 1:
        findings.append(
            Finding(
                id="sentinel.master_disagreement",
                severity=Severity.CRITICAL,
                category=Category.SENTINEL,
                title="Sentinels disagree on the current master address",
                explanation=(
                    "Disagreement about the master means a split-brain or an "
                    "in-progress failover; clients may write to the wrong node."
                ),
                evidence={"master_addrs": sorted(topo.master_addrs)},
                suggested_checks=[
                    "redis-cli -p <sentinel> SENTINEL get-master-addr-by-name <name>"
                ],
                suggested_fixes=["Investigate the failover state across all Sentinels"],
            )
        )

    for r in topo.replicas:
        if r.lag_seconds >= th.replica_lag_critical_seconds:
            findings.append(
                Finding(
                    id="sentinel.replica_lag_high",
                    severity=Severity.CRITICAL,
                    category=Category.SENTINEL,
                    title=f"Replica {r.addr} is {r.lag_seconds}s behind master",
                    explanation="A far-behind replica would lose recent writes if promoted.",
                    evidence={"replica": r.addr, "lag_seconds": r.lag_seconds},
                    suggested_checks=["redis-cli -p <sentinel> SENTINEL replicas <name>"],
                    suggested_fixes=["Investigate replica throughput / network"],
                    affected=[r.addr],
                )
            )
        if not r.reachable:
            findings.append(
                Finding(
                    id="sentinel.unreachable_replica",
                    severity=Severity.WARNING,
                    category=Category.SENTINEL,
                    title=f"Replica {r.addr} is unreachable",
                    explanation="An unreachable replica reduces redundancy and failover targets.",
                    evidence={"replica": r.addr, "flags": r.flags},
                    suggested_checks=["redis-cli -p <sentinel> SENTINEL replicas <name>"],
                    suggested_fixes=["Restore the replica"],
                    affected=[r.addr],
                )
            )

    if topo.failover_timeout_ms >= FAILOVER_TIMEOUT_UNUSUAL_MS:
        findings.append(
            Finding(
                id="sentinel.failover_timeout_unusual",
                severity=Severity.WARNING,
                category=Category.SENTINEL,
                title=f"failover-timeout is unusually high: {topo.failover_timeout_ms} ms",
                explanation=(
                    "A very high failover-timeout slows recovery, extending downtime "
                    "during a real failover."
                ),
                evidence={"failover_timeout_ms": topo.failover_timeout_ms},
                suggested_checks=["redis-cli -p <sentinel> SENTINEL master <name>"],
                suggested_fixes=["Lower failover-timeout to a sane value"],
            )
        )

    return findings
