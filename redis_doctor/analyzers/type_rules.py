"""Type distribution analysis (Section 9.6). Reads the keyspace sample."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..collectors.keyspace import tokenize_prefix
from ..models.finding import Category, Finding, Severity
from .base import Analyzer

if TYPE_CHECKING:
    from ..pipeline import RunContext

_COLLECTION_TYPES = {"list", "zset", "stream"}
MIXED_SECONDARY_SHARE = 0.1
UNTRIMMED_MIN_ELEMENTS = 1000
MIN_PREFIX_KEYS = 5


class TypeAnalyzer(Analyzer):
    name = "types"

    def analyze(self, ctx: RunContext) -> list[Finding]:
        data = ctx.collected.get("keyspace")
        if data is None or not data.sample.keys:
            return []

        seps = ctx.config.scan.prefix_separators
        depth = ctx.config.scan.prefix_depth
        keys = [k for k in data.sample.keys if k.type != "none"]
        confidence = data.sample.confidence

        # Type counts per prefix.
        per_prefix: dict[str, dict[str, int]] = {}
        for ki in keys:
            prefix = tokenize_prefix(ki.key, depth, seps)
            per_prefix.setdefault(prefix, {})
            per_prefix[prefix][ki.type] = per_prefix[prefix].get(ki.type, 0) + 1

        findings: list[Finding] = []
        mixed: list[str] = []
        for prefix, types in per_prefix.items():
            total = sum(types.values())
            if total < MIN_PREFIX_KEYS or len(types) < 2:
                continue
            ordered = sorted(types.values(), reverse=True)
            secondary_share = ordered[1] / total
            if secondary_share >= MIXED_SECONDARY_SHARE:
                mixed.append(prefix)

        if mixed:
            findings.append(
                Finding(
                    id="types.mixed_under_prefix",
                    severity=Severity.WARNING,
                    category=Category.TYPES,
                    confidence=confidence,
                    title=f"{len(mixed)} prefix(es) contain unexpectedly mixed value types",
                    explanation=(
                        "A single prefix holding multiple Redis types often indicates a "
                        "key naming collision or an accidental type change."
                    ),
                    evidence={"prefixes": mixed[:20]},
                    suggested_checks=["redis-doctor scan-keys <url>"],
                    suggested_fixes=["Verify the key schema for these prefixes"],
                    affected=[f"{p}:*" for p in mixed[:20]],
                )
            )

        untrimmed = [
            ki.key
            for ki in keys
            if ki.type in _COLLECTION_TYPES
            and ki.ttl_seconds == -1
            and (ki.element_count or 0) >= UNTRIMMED_MIN_ELEMENTS
        ]
        if untrimmed:
            findings.append(
                Finding(
                    id="types.untrimmed_collections",
                    severity=Severity.INFO,
                    category=Category.TYPES,
                    confidence=confidence,
                    title=f"{len(untrimmed)} growing collection(s) have no TTL or trim",
                    explanation=(
                        "Lists/zsets/streams that grow without a TTL or trim strategy "
                        "consume ever more memory."
                    ),
                    evidence={"count": len(untrimmed)},
                    suggested_checks=["redis-cli TYPE <key>"],
                    suggested_fixes=[
                        "Trim with LTRIM/ZREMRANGEBYRANK/XTRIM",
                        "Add a TTL where appropriate",
                    ],
                    affected=untrimmed[:20],
                )
            )

        return findings
