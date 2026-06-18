"""Orchestrates collect -> analyze -> score -> Report.

Collectors and analyzers are registered per module. Each module adds an entry
to the registry. `--only` / `--skip` filter modules by name.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from . import __version__
from .analyzers.base import Analyzer
from .analyzers.bigkey_rules import BigKeyAnalyzer
from .analyzers.client_rules import ClientAnalyzer
from .analyzers.config_rules import ConfigAnalyzer
from .analyzers.keyspace_rules import KeyspaceAnalyzer
from .analyzers.latency_rules import LatencyAnalyzer
from .analyzers.memory_rules import MemoryAnalyzer
from .analyzers.persistence_rules import PersistenceAnalyzer
from .analyzers.replication_rules import ReplicationAnalyzer
from .analyzers.security_rules import SecurityAnalyzer
from .analyzers.server_rules import ServerAnalyzer
from .analyzers.slowlog_rules import SlowlogAnalyzer
from .analyzers.stream_rules import StreamAnalyzer
from .analyzers.ttl_rules import TTLAnalyzer
from .analyzers.type_rules import TypeAnalyzer
from .collectors.base import Collector
from .collectors.clients import ClientCollector
from .collectors.config_values import ConfigValuesCollector
from .collectors.info import InfoCollector
from .collectors.keyspace import KeyspaceCollector
from .collectors.latency import LatencyCollector
from .collectors.memory import MemoryCollector
from .collectors.persistence import PersistenceCollector
from .collectors.replication import ReplicationCollector
from .collectors.security import SecurityCollector
from .collectors.slowlog import SlowlogCollector
from .collectors.streams import StreamCollector
from .config import Config
from .connection import SafeRedis
from .models.finding import Finding, Severity
from .models.report import Report, ReportSummary, SkippedModule
from .models.server import ServerInfo
from .rule_engine import RuleEngine
from .scoring import category_scores, health_score


@dataclass
class RunContext:
    """Shared state threaded through collectors and analyzers."""

    redis: SafeRedis
    config: Config
    options: dict[str, Any] = field(default_factory=dict)
    collected: dict[str, Any] = field(default_factory=dict)
    skipped: list[SkippedModule] = field(default_factory=list)
    raw_info: dict[str, Any] = field(default_factory=dict)
    sampled: bool = False
    rules: RuleEngine | None = None

    def skip(self, module: str, reason: str) -> None:
        self.skipped.append(SkippedModule(module=module, reason=reason))

    def info_fields(self) -> dict[str, Any]:
        """Return parsed INFO fields, fetching once and caching on first use."""
        if not self.raw_info:
            from .collectors.info import parse_info

            raw = self.redis.execute("INFO", "all")
            self.raw_info = parse_info(raw) if isinstance(raw, str) else dict(raw)
        return self.raw_info


@dataclass
class ModuleSpec:
    name: str
    collector: Collector | None
    analyzer: Analyzer | None


def _registry() -> list[ModuleSpec]:
    """All modules in run order."""
    return [
        ModuleSpec("server", InfoCollector(), ServerAnalyzer()),
        ModuleSpec("memory", MemoryCollector(), MemoryAnalyzer()),
        ModuleSpec("latency", LatencyCollector(), LatencyAnalyzer()),
        ModuleSpec("config", ConfigValuesCollector(), ConfigAnalyzer()),
        ModuleSpec("persistence", PersistenceCollector(), PersistenceAnalyzer()),
        ModuleSpec("replication", ReplicationCollector(), ReplicationAnalyzer()),
        ModuleSpec("keyspace", KeyspaceCollector(), KeyspaceAnalyzer()),
        # ttl/bigkey/types reuse the keyspace sample (no extra Redis reads).
        ModuleSpec("ttl", None, TTLAnalyzer()),
        ModuleSpec("bigkey", None, BigKeyAnalyzer()),
        ModuleSpec("types", None, TypeAnalyzer()),
        ModuleSpec("streams", StreamCollector(), StreamAnalyzer()),
        ModuleSpec("clients", ClientCollector(), ClientAnalyzer()),
        ModuleSpec("slowlog", SlowlogCollector(), SlowlogAnalyzer()),
        ModuleSpec("security", SecurityCollector(), SecurityAnalyzer()),
    ]


# Analyzer modules that need another module's collected data to run.
_DEPENDENCIES = {
    "ttl": "keyspace",
    "bigkey": "keyspace",
    "types": "keyspace",
    "streams": "keyspace",
}


def _filter_modules(
    specs: list[ModuleSpec],
    only: list[str] | None,
    skip: list[str] | None,
    disable_dependencies: bool = False,
) -> list[ModuleSpec]:
    selected = {s.name for s in specs}
    if only:
        selected = {name for name in selected if name in only}
    if skip:
        selected -= set(skip)
    # Pull in collector dependencies (e.g. ttl needs the keyspace sample).
    if not disable_dependencies:
        for name in list(selected):
            dep = _DEPENDENCIES.get(name)
            if dep and dep not in selected:
                selected.add(dep)
    return [s for s in specs if s.name in selected]


def run_pipeline(
    redis: SafeRedis,
    config: Config,
    *,
    options: dict[str, Any] | None = None,
    only: list[str] | None = None,
    skip: list[str] | None = None,
    disable_dependencies: bool = False,
) -> Report:
    start = time.monotonic()
    engine = RuleEngine.from_config(config)
    ctx = RunContext(redis=redis, config=config, options=options or {}, rules=engine)

    specs = _filter_modules(_registry(), only, skip, disable_dependencies)

    # Collect phase: store each collector's result under its module name.
    for spec in specs:
        if spec.collector is None:
            continue
        result = spec.collector.run(ctx)
        ctx.collected[spec.collector.name] = result

    # Analyze phase.
    findings: list[Finding] = []
    for spec in specs:
        if spec.analyzer is None:
            continue
        try:
            findings.extend(spec.analyzer.analyze(ctx))
        except Exception as e:  # one analyzer failing must not abort the run
            ctx.skip(spec.name, f"analyzer error: {e}")

    findings = [f for f in findings if engine.is_active(f.id)]

    server: ServerInfo = ctx.collected.get("info") or ServerInfo()
    duration = time.monotonic() - start

    return Report(
        target=redis.target.redacted_url(),
        generated_at=datetime.now(UTC),
        redis_doctor_version=__version__,
        duration_seconds=round(duration, 3),
        sampled=ctx.sampled,
        health_score=health_score(findings),
        category_scores=category_scores(findings),
        summary=_summarize(findings),
        server=server,
        findings=findings,
        skipped=ctx.skipped,
        stats=_build_stats(ctx),
    )


def build_report(
    target: str,
    findings: list[Finding],
    *,
    config: Config,
    server: ServerInfo | None = None,
    stats: dict[str, Any] | None = None,
    skipped: list[SkippedModule] | None = None,
) -> Report:
    """Assemble a Report from a precomputed list of findings (sentinel/cluster)."""
    engine = RuleEngine.from_config(config)
    findings = [f for f in findings if engine.is_active(f.id)]
    return Report(
        target=target,
        generated_at=datetime.now(UTC),
        redis_doctor_version=__version__,
        health_score=health_score(findings),
        category_scores=category_scores(findings),
        summary=_summarize(findings),
        server=server or ServerInfo(),
        findings=findings,
        skipped=skipped or [],
        stats=stats or {},
    )


def _summarize(findings: list[Finding]) -> ReportSummary:
    s = ReportSummary()
    for f in findings:
        if f.severity == Severity.CRITICAL:
            s.critical += 1
        elif f.severity == Severity.WARNING:
            s.warning += 1
        else:
            s.info += 1
    return s


def _build_stats(ctx: RunContext) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    info: ServerInfo | None = ctx.collected.get("info")
    if info is not None:
        stats["server"] = {
            "redis_version": info.redis_version,
            "role": info.role,
            "used_memory_bytes": info.used_memory_bytes,
            "maxmemory_bytes": info.maxmemory_bytes,
            "total_keys": info.total_keys,
        }

    keyspace = ctx.collected.get("keyspace")
    if keyspace is not None:
        s = keyspace.sample
        stats["keyspace"] = {
            "dbsize": keyspace.dbsize,
            "scanned": s.scanned,
            "estimated_total": s.estimated_total,
            "confidence": s.confidence.value,
            "duration_seconds": s.duration_seconds,
            "complete": s.complete,
            "type_distribution": keyspace.type_distribution,
            "top_prefixes_by_count": [
                {"prefix": p.prefix, "count": p.count, "memory_bytes": p.memory_bytes}
                for p in keyspace.by_count[:10]
            ],
            "top_prefixes_by_memory": [
                {"prefix": p.prefix, "count": p.count, "memory_bytes": p.memory_bytes}
                for p in keyspace.by_memory[:10]
            ],
            # Largest sampled keys (metadata only) for the Explore views.
            "sampled_keys": [
                {
                    "key": ki.key,
                    "type": ki.type,
                    "ttl": ki.ttl_seconds,
                    "memory": ki.memory_bytes,
                    "size": ki.element_count,
                }
                for ki in sorted(s.keys, key=lambda k: k.memory_bytes or 0, reverse=True)[:500]
            ],
        }

    clients = ctx.collected.get("clients")
    if clients is not None:
        stats["clients"] = _client_stats(clients, info)

    streams = ctx.collected.get("streams")
    if streams:
        stats["streams"] = [
            {
                "name": st.name,
                "length": st.length,
                "groups": [
                    {
                        "name": g.name,
                        "consumers": g.consumers,
                        "pending": g.pending,
                        "lag": g.lag,
                        "consumer_list": [
                            {"name": c.name, "pending": c.pending, "idle_ms": c.idle_ms}
                            for c in g.consumer_list
                        ],
                    }
                    for g in st.groups
                ],
            }
            for st in streams
        ]

    slowlog = ctx.collected.get("slowlog")
    if slowlog:
        from collections import Counter

        entries = slowlog.get("entries", [])
        cmd_freq = Counter(e.command for e in entries)
        durations = [e.duration_us for e in entries]
        stats["slowlog"] = {
            "length": slowlog.get("length", 0),
            "sampled": len(entries),
            "max_duration_us": max(durations) if durations else 0,
            "avg_duration_us": int(sum(durations) / len(durations)) if durations else 0,
            "command_frequency": dict(cmd_freq.most_common(10)),
        }
    return stats


def _client_stats(clients: list, info: ServerInfo | None) -> dict[str, Any]:
    from collections import Counter

    total = len(clients)
    unnamed = sum(1 for c in clients if not c.name)
    idle_1h = sum(1 for c in clients if c.idle_seconds >= 3600)
    by_command = Counter(c.last_cmd for c in clients if c.last_cmd)
    return {
        "total": total,
        "blocked": info.blocked_clients if info else 0,
        "unnamed": unnamed,
        "idle_over_1h": idle_1h,
        "top_commands": dict(by_command.most_common(5)),
    }
