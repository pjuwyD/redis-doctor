"""TTL analysis (Section 9.4). Reads the keyspace sample."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..collectors.keyspace import tokenize_prefix
from ..models.finding import Category, Finding, Severity
from .base import Analyzer

if TYPE_CHECKING:
    from ..pipeline import RunContext

# Keyword -> logical TTL category, matched against a key's first token.
_LOCK = {"lock", "locks", "mutex", "leader"}
_SESSION = {"session", "sessions", "sess", "temp", "tmp"}
_CACHE = {"cache", "caches", "cached"}
_TOKEN = {
    "token",
    "tokens",
    "otp",
    "verify",
    "verification",
    "reset",
    "pwreset",
    "passwordreset",
    "jwt",
    "confirm",
    "magic",
}

CRITICAL_SHARE = 0.5
CACHE_PERMANENT_SHARE = 0.7
INCONSISTENT_LOW = 0.1
INCONSISTENT_HIGH = 0.9


@dataclass
class _Tally:
    total: int = 0
    no_ttl: int = 0
    keys: list[str] = field(default_factory=list)

    @property
    def share(self) -> float:
        return self.no_ttl / self.total if self.total else 0.0


def _category(token: str) -> str | None:
    t = token.lower()
    if t in _LOCK:
        return "lock"
    if t in _SESSION:
        return "session"
    if t in _CACHE:
        return "cache"
    if t in _TOKEN:
        return "token"
    return None


class TTLAnalyzer(Analyzer):
    name = "ttl"

    def analyze(self, ctx: RunContext) -> list[Finding]:
        data = ctx.collected.get("keyspace")
        if data is None or not data.sample.keys:
            return []

        seps = ctx.config.scan.prefix_separators
        depth = ctx.config.scan.prefix_depth
        keys = [k for k in data.sample.keys if k.type != "none"]
        confidence = data.sample.confidence

        tallies: dict[str, _Tally] = {c: _Tally() for c in ("lock", "session", "cache", "token")}
        prefix_tallies: dict[str, _Tally] = {}

        for ki in keys:
            token = tokenize_prefix(ki.key, 1, seps)
            cat = _category(token)
            if cat:
                t = tallies[cat]
                t.total += 1
                if ki.ttl_seconds == -1:
                    t.no_ttl += 1
                    if len(t.keys) < 20:
                        t.keys.append(ki.key)

            prefix = tokenize_prefix(ki.key, depth, seps)
            pt = prefix_tallies.setdefault(prefix, _Tally())
            pt.total += 1
            if ki.ttl_seconds == -1:
                pt.no_ttl += 1

        findings: list[Finding] = []
        self._apply_expectations(ctx, keys, tallies)

        self._category_finding(
            findings,
            tallies["lock"],
            confidence,
            fid="ttl.locks_without_ttl",
            severity=Severity.CRITICAL,
            label="lock:*",
            why="Locks without a TTL can deadlock workflows permanently if a holder dies.",
            min_share=CRITICAL_SHARE,
        )
        self._category_finding(
            findings,
            tallies["session"],
            confidence,
            fid="ttl.sessions_without_ttl",
            severity=Severity.CRITICAL,
            label="session/temp",
            why="Session/temp keys without a TTL accumulate forever and leak memory.",
            min_share=CRITICAL_SHARE,
        )
        self._category_finding(
            findings,
            tallies["token"],
            confidence,
            fid="ttl.tokens_without_ttl",
            severity=Severity.CRITICAL,
            label="token/OTP",
            why="Tokens/OTPs without a TTL stay valid forever, a security risk.",
            min_share=CRITICAL_SHARE,
        )
        self._category_finding(
            findings,
            tallies["cache"],
            confidence,
            fid="ttl.cache_permanent",
            severity=Severity.WARNING,
            label="cache:*",
            why="A cache dominated by permanent keys never expires and grows unbounded.",
            min_share=CACHE_PERMANENT_SHARE,
        )

        self._excessive_ttl(ctx, findings, keys)
        self._inconsistent(findings, prefix_tallies, confidence)
        return findings

    def _category_finding(
        self, findings, tally, confidence, *, fid, severity, label, why, min_share
    ):
        if tally.no_ttl > 0 and tally.share >= min_share:
            findings.append(
                Finding(
                    id=fid,
                    severity=severity,
                    category=Category.TTL,
                    confidence=confidence,
                    title=f"{tally.share:.0%} of {label} keys have no TTL",
                    explanation=why,
                    evidence={
                        "no_ttl": tally.no_ttl,
                        "total_in_category": tally.total,
                        "share": round(tally.share, 3),
                    },
                    suggested_checks=["redis-cli TTL <key>"],
                    suggested_fixes=[
                        "Set an appropriate EXPIRE/SETEX on these keys",
                        "Ensure code paths that create them set a TTL",
                    ],
                    affected=tally.keys,
                )
            )

    def _apply_expectations(self, ctx, keys, tallies) -> None:
        """ttl_required expectations fold matching no-TTL keys into a category."""
        for exp in ctx.config.ttl_expectations:
            if not exp.ttl_required:
                continue
            token = tokenize_prefix(exp.pattern, 1, ctx.config.scan.prefix_separators)
            cat = _category(token) or "session"
            for ki in keys:
                if fnmatch.fnmatch(ki.key, exp.pattern) and ki.ttl_seconds == -1:
                    t = tallies[cat]
                    t.total += 1
                    t.no_ttl += 1
                    if len(t.keys) < 20:
                        t.keys.append(ki.key)

    def _excessive_ttl(self, ctx, findings, keys) -> None:
        offenders: list[str] = []
        max_observed = 0
        for exp in ctx.config.ttl_expectations:
            if exp.max_ttl_seconds is None:
                continue
            for ki in keys:
                if ki.ttl_seconds > exp.max_ttl_seconds and fnmatch.fnmatch(ki.key, exp.pattern):
                    offenders.append(ki.key)
                    max_observed = max(max_observed, ki.ttl_seconds)
        if offenders:
            findings.append(
                Finding(
                    id="ttl.excessive_ttl",
                    severity=Severity.WARNING,
                    category=Category.TTL,
                    title=f"{len(offenders)} keys have a TTL beyond the expected maximum",
                    explanation=(
                        "Temporary-looking keys with very long TTLs occupy memory far "
                        "longer than intended."
                    ),
                    evidence={"count": len(offenders), "max_ttl_seconds": max_observed},
                    suggested_checks=["redis-cli TTL <key>"],
                    suggested_fixes=["Lower the TTL to the intended lifetime"],
                    affected=offenders[:20],
                )
            )

    def _inconsistent(self, findings, prefix_tallies, confidence) -> None:
        mixed: list[str] = []
        for prefix, t in prefix_tallies.items():
            if t.total < 5:
                continue
            if INCONSISTENT_LOW < t.share < INCONSISTENT_HIGH:
                mixed.append(prefix)
        if mixed:
            findings.append(
                Finding(
                    id="ttl.inconsistent_within_prefix",
                    severity=Severity.WARNING,
                    category=Category.TTL,
                    confidence=confidence,
                    title=f"{len(mixed)} prefix(es) mix keys with and without TTL",
                    explanation=(
                        "Inconsistent TTLs within one prefix usually signal a bug where "
                        "some code paths forget to set expiry."
                    ),
                    evidence={"prefixes": mixed[:20]},
                    suggested_checks=["redis-doctor scan-keys <url>"],
                    suggested_fixes=["Make TTL handling consistent across the prefix"],
                    affected=[f"{p}:*" for p in mixed[:20]],
                )
            )
