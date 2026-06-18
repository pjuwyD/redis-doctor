"""Client analysis analyzer (Section 9.8)."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from ..models.finding import Category, Finding, Severity
from .base import Analyzer

if TYPE_CHECKING:
    from ..pipeline import RunContext

OUTPUT_BUFFER_LARGE = 10 * 1024 * 1024
UNNAMED_SHARE = 0.8
UNNAMED_MIN_CLIENTS = 20
SAME_IP_SHARE = 0.5
SAME_IP_MIN = 50


def _ip(addr: str) -> str:
    return addr.rsplit(":", 1)[0] if addr else ""


class ClientAnalyzer(Analyzer):
    name = "clients"

    def analyze(self, ctx: RunContext) -> list[Finding]:
        clients = ctx.collected.get("clients")
        if clients is None:
            return []

        th = ctx.config.thresholds
        findings: list[Finding] = []
        total = len(clients)
        if total == 0:
            return []

        # Note: connections-near-maxclients and blocked-clients are reported by the
        # server module (server.high_client_count / server.blocked_clients) from
        # INFO, to avoid duplicate findings. This module covers the per-connection
        # details instead.

        idle = [c for c in clients if c.idle_seconds >= th.idle_client_warning_seconds]
        if len(idle) >= th.idle_client_critical_count:
            findings.append(self._idle_finding(idle, th, Severity.CRITICAL))
        elif len(idle) >= th.idle_client_warning_count:
            findings.append(self._idle_finding(idle, th, Severity.WARNING))

        big_buffer = [c for c in clients if c.output_buffer >= OUTPUT_BUFFER_LARGE]
        if big_buffer:
            findings.append(
                Finding(
                    id="clients.output_buffer_large",
                    severity=Severity.CRITICAL,
                    category=Category.CLIENTS,
                    title=f"{len(big_buffer)} client(s) have a large output buffer",
                    explanation=(
                        "Large client output buffers consume memory and can trigger "
                        "client eviction or OOM; often a slow consumer."
                    ),
                    evidence={
                        "count": len(big_buffer),
                        "max_buffer_bytes": max(c.output_buffer for c in big_buffer),
                    },
                    suggested_checks=["redis-cli CLIENT LIST"],
                    suggested_fixes=["Find slow consumers", "Check client-output-buffer-limit"],
                    affected=[c.addr for c in big_buffer[:20]],
                )
            )

        unnamed = [c for c in clients if not c.name]
        if total >= UNNAMED_MIN_CLIENTS and len(unnamed) / total >= UNNAMED_SHARE:
            findings.append(
                Finding(
                    id="clients.unnamed",
                    severity=Severity.WARNING,
                    category=Category.CLIENTS,
                    title=f"{len(unnamed) / total:.0%} of clients have no name set",
                    explanation=(
                        "Unnamed clients make it hard to attribute connections to "
                        "services during incidents. Use CLIENT SETNAME."
                    ),
                    evidence={"unnamed": len(unnamed), "total": total},
                    suggested_checks=["redis-cli CLIENT LIST"],
                    suggested_fixes=["Call CLIENT SETNAME in each service's connection setup"],
                )
            )

        ip_counts = Counter(_ip(c.addr) for c in clients if c.addr)
        if ip_counts:
            top_ip, top_count = ip_counts.most_common(1)[0]
            if top_count >= SAME_IP_MIN and top_count / total >= SAME_IP_SHARE:
                findings.append(
                    Finding(
                        id="clients.same_ip_many",
                        severity=Severity.WARNING,
                        category=Category.CLIENTS,
                        title=f"{top_count} clients connect from a single IP ({top_ip})",
                        explanation=(
                            "Many connections from one IP can indicate a missing "
                            "connection pool or a misbehaving client."
                        ),
                        evidence={"ip": top_ip, "count": top_count, "total": total},
                        suggested_checks=["redis-cli CLIENT LIST"],
                        suggested_fixes=["Use a connection pool on that host"],
                        affected=[top_ip],
                    )
                )

        return findings

    def _idle_finding(self, idle, th, severity) -> Finding:
        return Finding(
            id="clients.idle_many",
            severity=severity,
            category=Category.CLIENTS,
            title=f"{len(idle)} clients idle longer than {th.idle_client_warning_seconds}s",
            explanation=(
                "Many long-idle clients hold connections and memory; with timeout=0 "
                "they never get reaped."
            ),
            evidence={
                "idle_clients": len(idle),
                "idle_threshold_seconds": th.idle_client_warning_seconds,
            },
            suggested_checks=["redis-cli CLIENT LIST"],
            suggested_fixes=["Set a connection timeout", "Fix clients that leak idle connections"],
        )
