"""Cluster analyzer (Section 9.16). Operates on ClusterData."""

from __future__ import annotations

from ..collectors.cluster import ClusterData
from ..models.finding import Category, Finding, Severity

UNEVEN_RATIO = 2.0


def analyze_cluster(data: ClusterData) -> list[Finding]:
    findings: list[Finding] = []
    if not data.enabled:
        return findings

    if data.uncovered_slots > 0 or data.state != "ok":
        findings.append(
            Finding(
                id="cluster.uncovered_slots",
                severity=Severity.CRITICAL,
                category=Category.CLUSTER,
                title=f"{data.uncovered_slots} hash slots are not covered",
                explanation=(
                    "Uncovered slots mean part of the keyspace is unreachable; "
                    "commands for those slots fail."
                ),
                evidence={
                    "uncovered_slots": data.uncovered_slots,
                    "cluster_state": data.state,
                    "slots_assigned": data.slots_assigned,
                },
                suggested_checks=["redis-cli CLUSTER INFO", "redis-cli CLUSTER SLOTS"],
                suggested_fixes=["Reassign slots with cluster fix", "Restore failed nodes"],
            )
        )

    failed = [n for n in data.nodes if n.failed]
    if failed:
        findings.append(
            Finding(
                id="cluster.failed_node",
                severity=Severity.CRITICAL,
                category=Category.CLUSTER,
                title=f"{len(failed)} cluster node(s) report a fail state",
                explanation="A failed node removes its shard's availability or redundancy.",
                evidence={"failed_nodes": [n.addr for n in failed]},
                suggested_checks=["redis-cli CLUSTER NODES"],
                suggested_fixes=["Investigate and restore the failed nodes"],
                affected=[n.addr for n in failed],
            )
        )

    replica_master_ids = {n.master_id for n in data.nodes if n.role == "slave"}
    without_replica = [m for m in data.masters if m.id not in replica_master_ids and not m.failed]
    if without_replica:
        findings.append(
            Finding(
                id="cluster.master_without_replica",
                severity=Severity.WARNING,
                category=Category.CLUSTER,
                title=f"{len(without_replica)} master(s) have no replica",
                explanation=(
                    "A master without a replica has no failover target; its shard goes "
                    "down if it fails."
                ),
                evidence={"masters": [m.addr for m in without_replica]},
                suggested_checks=["redis-cli CLUSTER NODES"],
                suggested_fixes=["Add a replica to each master"],
                affected=[m.addr for m in without_replica],
            )
        )

    reachable_masters = [m for m in data.masters if m.reachable and not m.failed]
    _uneven(findings, reachable_masters, "keys", "cluster.uneven_keys", "key")
    _uneven(findings, reachable_masters, "used_memory", "cluster.uneven_memory", "memory")
    return findings


def _uneven(findings, masters, attr, fid, label) -> None:
    values = [getattr(m, attr) for m in masters]
    if len(values) < 2 or max(values) == 0:
        return
    lo = min(values)
    hi = max(values)
    if lo == 0 or hi / lo >= UNEVEN_RATIO:
        findings.append(
            Finding(
                id=fid,
                severity=Severity.WARNING,
                category=Category.CLUSTER,
                title=f"Uneven {label} distribution across masters",
                explanation=(
                    f"A large imbalance in {label} across shards causes hotspots and "
                    "inefficient resource use."
                ),
                evidence={
                    "min": lo,
                    "max": hi,
                    "by_node": {m.addr: getattr(m, attr) for m in masters},
                },
                suggested_checks=["redis-cli --cluster check <host>:<port>"],
                suggested_fixes=["Rebalance slots across masters"],
            )
        )
