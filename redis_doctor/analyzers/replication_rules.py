"""Replication analyzer (Section 9.13)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.finding import Category, Finding, Severity
from .base import Analyzer

if TYPE_CHECKING:
    from ..pipeline import RunContext


class ReplicationAnalyzer(Analyzer):
    name = "replication"

    def analyze(self, ctx: RunContext) -> list[Finding]:
        data = ctx.collected.get("replication")
        if data is None:
            return []

        th = ctx.config.thresholds
        findings: list[Finding] = []
        is_replica = data.role == "slave"

        if is_replica:
            if data.master_link_status and data.master_link_status != "up":
                findings.append(
                    Finding(
                        id="replication.link_down",
                        severity=Severity.CRITICAL,
                        category=Category.REPLICATION,
                        title="Replica link to master is down",
                        explanation=(
                            "The replica cannot reach its master, so it is serving "
                            "stale data and cannot take over cleanly."
                        ),
                        evidence={"master_link_status": data.master_link_status},
                        suggested_checks=["redis-cli INFO replication"],
                        suggested_fixes=["Check network/auth between replica and master"],
                    )
                )

            lag = data.master_last_io_seconds_ago
            if lag >= 0:
                self._lag_finding(findings, th, lag, role="replica")

            if data.slave_read_only == 0:
                findings.append(
                    Finding(
                        id="replication.replica_writable",
                        severity=Severity.CRITICAL,
                        category=Category.REPLICATION,
                        title="Replica is writable (replica-read-only is off)",
                        explanation=(
                            "A writable replica accepts writes that diverge from the "
                            "master and are lost on the next resync."
                        ),
                        evidence={"slave_read_only": 0},
                        suggested_checks=["redis-cli CONFIG GET replica-read-only"],
                        suggested_fixes=["Set replica-read-only yes"],
                    )
                )
        else:
            for slave in data.slaves:
                try:
                    lag = int(slave.get("lag", 0))
                except (ValueError, TypeError):
                    lag = 0
                self._lag_finding(
                    findings, th, lag, role="master", who=f"{slave.get('ip')}:{slave.get('port')}"
                )

            if data.connected_slaves == 0 and ctx.options.get("expect_replicas"):
                findings.append(
                    Finding(
                        id="replication.no_replicas",
                        severity=Severity.WARNING,
                        category=Category.REPLICATION,
                        title="Master has no connected replicas",
                        explanation=(
                            "With no replicas, there is no failover target and no read "
                            "scaling; a master failure means downtime."
                        ),
                        evidence={"connected_slaves": 0},
                        suggested_checks=["redis-cli INFO replication"],
                        suggested_fixes=["Attach at least one replica for HA"],
                    )
                )

        return findings

    def _lag_finding(self, findings, th, lag, role, who: str | None = None) -> None:
        if lag >= th.replica_lag_critical_seconds:
            severity = Severity.CRITICAL
        elif lag >= th.replica_lag_warning_seconds:
            severity = Severity.WARNING
        else:
            return
        target = who or "replica"
        findings.append(
            Finding(
                id="replication.lag_high",
                severity=severity,
                category=Category.REPLICATION,
                title=f"Replication lag is high ({lag}s) on {target}",
                explanation=(
                    "High replication lag means the replica is far behind the master; "
                    "a failover would lose recent writes."
                ),
                evidence={"lag_seconds": lag, "role_observed": role},
                suggested_checks=["redis-cli INFO replication"],
                suggested_fixes=[
                    "Investigate network/throughput between master and replica",
                    "Check replica load",
                ],
                affected=[target] if who else [],
            )
        )
