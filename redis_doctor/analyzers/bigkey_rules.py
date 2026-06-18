"""Big key detection (Section 9.5). Reads the keyspace sample."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.finding import Category, Finding, Severity
from .base import Analyzer

if TYPE_CHECKING:
    from ..pipeline import RunContext

MAX_FINDINGS = 50
_COLLECTION_TYPES = {"list", "set", "zset", "hash", "stream"}

_FIXES = [
    "Split the value by shard/customer/time",
    "Add a TTL or trim the collection (XTRIM for streams)",
    "Compress the value or avoid huge JSON blobs",
]


class BigKeyAnalyzer(Analyzer):
    name = "bigkey"

    def analyze(self, ctx: RunContext) -> list[Finding]:
        data = ctx.collected.get("keyspace")
        if data is None or not data.sample.keys:
            return []

        th = ctx.config.thresholds
        big_bytes = int(th.big_key_mb * 1024 * 1024)
        huge_bytes = int(th.huge_key_mb * 1024 * 1024)

        findings: list[Finding] = []
        # Largest keys first so the cap keeps the worst offenders.
        keys = sorted(
            data.sample.keys,
            key=lambda k: (k.memory_bytes or 0, k.element_count or 0),
            reverse=True,
        )

        for ki in keys:
            if len(findings) >= MAX_FINDINGS:
                break
            mem = ki.memory_bytes or 0
            count = ki.element_count or 0

            if mem > huge_bytes:
                findings.append(self._mem_finding(ki, mem, Severity.CRITICAL, "huge_memory"))
            elif mem > big_bytes:
                findings.append(self._mem_finding(ki, mem, Severity.WARNING, "big_memory"))

            if ki.type in _COLLECTION_TYPES:
                if count > th.huge_collection:
                    findings.append(
                        self._coll_finding(ki, count, Severity.CRITICAL, "huge_collection")
                    )
                elif count > th.large_collection:
                    findings.append(
                        self._coll_finding(ki, count, Severity.WARNING, "large_collection")
                    )

        return findings

    def _mem_finding(self, ki, mem, severity, suffix) -> Finding:
        mb = mem / (1024 * 1024)
        return Finding(
            id=f"bigkey.{suffix}",
            severity=severity,
            category=Category.BIGKEY,
            title=f"Key {ki.key} is {mb:.1f} MB ({ki.type})",
            explanation=(
                "Large keys make single operations slow and block the event loop; "
                "they also complicate sharding and migration."
            ),
            evidence={"key": ki.key, "type": ki.type, "memory_bytes": mem},
            suggested_checks=[f"redis-cli MEMORY USAGE {ki.key}"],
            suggested_fixes=_FIXES,
            affected=[ki.key],
        )

    def _coll_finding(self, ki, count, severity, suffix) -> Finding:
        return Finding(
            id=f"bigkey.{suffix}",
            severity=severity,
            category=Category.BIGKEY,
            title=f"Collection {ki.key} has {count:,} elements ({ki.type})",
            explanation=(
                "Very large collections make range/scan operations slow and risk "
                "blocking the server."
            ),
            evidence={"key": ki.key, "type": ki.type, "element_count": count},
            suggested_checks=[f"redis-cli TYPE {ki.key}"],
            suggested_fixes=_FIXES,
            affected=[ki.key],
        )
