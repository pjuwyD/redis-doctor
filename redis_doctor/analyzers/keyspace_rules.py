"""Keyspace overview analyzer (Section 9.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.finding import Category, Confidence, Finding, Severity
from .base import Analyzer

if TYPE_CHECKING:
    from ..pipeline import RunContext

DOMINANT_SHARE = 0.5
HIGH_KEY_COUNT = 1_000_000
HIGH_NO_TTL_SHARE = 0.5


class KeyspaceAnalyzer(Analyzer):
    name = "keyspace"

    def analyze(self, ctx: RunContext) -> list[Finding]:
        data = ctx.collected.get("keyspace")
        if data is None or data.sample.scanned == 0:
            return []

        findings: list[Finding] = []
        scanned = data.sample.scanned
        confidence = data.sample.confidence

        if data.by_count:
            top = data.by_count[0]
            share = top.count / scanned
            if share > DOMINANT_SHARE:
                findings.append(
                    Finding(
                        id="keyspace.dominant_prefix",
                        severity=Severity.INFO,
                        category=Category.KEYSPACE,
                        confidence=confidence,
                        title=f"Prefix {top.prefix}:* dominates the keyspace ({share:.0%})",
                        explanation=(
                            "One prefix makes up most of the keyspace. This is often "
                            "expected, but worth confirming it is intentional."
                        ),
                        evidence={
                            "prefix": top.prefix,
                            "share": round(share, 3),
                            "count_in_sample": top.count,
                        },
                        suggested_checks=["redis-doctor scan-keys <url>"],
                        suggested_fixes=[],
                        affected=[f"{top.prefix}:*"],
                    )
                )

        no_ttl = sum(1 for k in data.sample.keys if k.ttl_seconds == -1)
        no_ttl_share = no_ttl / scanned if scanned else 0
        if data.dbsize >= HIGH_KEY_COUNT and no_ttl_share > HIGH_NO_TTL_SHARE:
            findings.append(
                Finding(
                    id="keyspace.high_key_count",
                    severity=Severity.WARNING,
                    category=Category.KEYSPACE,
                    confidence=Confidence.MEDIUM,
                    title=f"Very large keyspace ({data.dbsize:,} keys) with many keys lacking TTL",
                    explanation=(
                        "A very large keyspace where most keys have no TTL grows "
                        "unbounded and risks memory exhaustion."
                    ),
                    evidence={
                        "dbsize": data.dbsize,
                        "no_ttl_share_in_sample": round(no_ttl_share, 3),
                    },
                    suggested_checks=["redis-doctor scan-keys <url>"],
                    suggested_fixes=[
                        "Add TTLs to ephemeral keys",
                        "Set a maxmemory eviction policy",
                    ],
                )
            )

        return findings
