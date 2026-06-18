"""Server summary analyzer (Section 9.1)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models.finding import Category, Finding, Severity
from .base import Analyzer

if TYPE_CHECKING:
    from ..pipeline import RunContext


def _major_version(version: str) -> int:
    m = re.match(r"(\d+)", version)
    return int(m.group(1)) if m else 0


class ServerAnalyzer(Analyzer):
    name = "server"

    def analyze(self, ctx: RunContext) -> list[Finding]:
        info = ctx.collected.get("info")
        if info is None:
            return []

        findings: list[Finding] = []
        th = ctx.config.thresholds

        major = _major_version(info.redis_version)
        if major and major < 7:
            findings.append(
                Finding(
                    id="server.version_outdated",
                    severity=Severity.WARNING,
                    category=Category.SERVER,
                    title=f"Redis {info.redis_version} is an outdated major version",
                    explanation=(
                        "Redis versions before 7 miss performance, security, and "
                        "functionality fixes present in current releases."
                    ),
                    evidence={"redis_version": info.redis_version, "major": major},
                    suggested_checks=["redis-cli INFO server"],
                    suggested_fixes=["Plan an upgrade to a supported Redis 7.x release"],
                )
            )

        if 0 < info.uptime_seconds < 3600:
            findings.append(
                Finding(
                    id="server.recent_restart",
                    severity=Severity.INFO,
                    category=Category.SERVER,
                    title="Redis restarted within the last hour",
                    explanation=(
                        "A recent restart can explain cold caches, dropped "
                        "connections, or lost in-memory state."
                    ),
                    evidence={"uptime_seconds": info.uptime_seconds},
                    suggested_checks=["redis-cli INFO server | grep uptime"],
                    suggested_fixes=["Confirm the restart was intentional"],
                )
            )

        expect_role = ctx.options.get("expect_role")
        if expect_role and info.role != expect_role:
            findings.append(
                Finding(
                    id="server.role_unexpected",
                    severity=Severity.INFO,
                    category=Category.SERVER,
                    title=f"Role is {info.role}, expected {expect_role}",
                    explanation="The instance is serving a different role than expected.",
                    evidence={"role": info.role, "expected": expect_role},
                    suggested_checks=["redis-cli INFO replication"],
                    suggested_fixes=["Verify failover state and client routing"],
                )
            )

        if info.maxclients and info.connected_clients > 0.8 * info.maxclients:
            findings.append(
                Finding(
                    id="server.high_client_count",
                    severity=Severity.WARNING,
                    category=Category.SERVER,
                    title="Connected clients are near the maxclients limit",
                    explanation=(
                        "When connected clients reach maxclients, Redis rejects new "
                        "connections, causing application errors."
                    ),
                    evidence={
                        "connected_clients": info.connected_clients,
                        "maxclients": info.maxclients,
                    },
                    suggested_checks=["redis-cli INFO clients", "redis-cli CONFIG GET maxclients"],
                    suggested_fixes=[
                        "Investigate connection leaks",
                        "Use connection pooling",
                        "Raise maxclients if the host can support it",
                    ],
                )
            )

        if info.blocked_clients >= th.blocked_client_warning:
            findings.append(
                Finding(
                    id="server.blocked_clients",
                    severity=Severity.WARNING,
                    category=Category.SERVER,
                    title=f"{info.blocked_clients} clients are blocked",
                    explanation=(
                        "Blocked clients are waiting on BLPOP/BRPOP/XREAD-style "
                        "commands; a persistently high count can indicate a stalled "
                        "consumer or queue backup."
                    ),
                    evidence={"blocked_clients": info.blocked_clients},
                    suggested_checks=["redis-cli INFO clients", "redis-cli CLIENT LIST"],
                    suggested_fixes=["Check consumers that issue blocking commands"],
                )
            )

        if info.evicted_keys > 0:
            findings.append(
                Finding(
                    id="server.evictions_occurring",
                    severity=Severity.WARNING,
                    category=Category.SERVER,
                    title=f"{info.evicted_keys} keys have been evicted",
                    explanation=(
                        "Evictions mean Redis is dropping data to stay under "
                        "maxmemory. Cached data is being lost and may degrade hit rates."
                    ),
                    evidence={"evicted_keys": info.evicted_keys},
                    suggested_checks=[
                        "redis-cli INFO stats | grep evicted",
                        "redis-cli INFO memory",
                    ],
                    suggested_fixes=[
                        "Increase maxmemory",
                        "Reduce data footprint",
                        "Review the eviction policy",
                    ],
                )
            )

        return findings
