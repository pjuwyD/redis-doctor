"""Markdown output (Section 7.3)."""

from __future__ import annotations

from ..models.finding import Severity
from ..models.report import Report
from .terminal import human_bytes, human_duration

_SEVERITY_ORDER = [Severity.CRITICAL, Severity.WARNING, Severity.INFO]
_SEVERITY_HEADING = {
    Severity.CRITICAL: "Critical findings",
    Severity.WARNING: "Warnings",
    Severity.INFO: "Info",
}


def render_markdown(report: Report) -> str:
    s = report.server
    out: list[str] = []
    out.append("# Redis Doctor Report")
    out.append("")
    out.append(f"- **Target:** {report.target}")
    out.append(f"- **Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    out.append(f"- **redis-doctor:** {report.redis_doctor_version}")
    out.append(f"- **Health score:** {report.health_score}/100")
    out.append(
        f"- **Findings:** {report.summary.critical} critical, "
        f"{report.summary.warning} warning, {report.summary.info} info"
    )
    out.append("")

    out.append("## Server")
    out.append("")
    out.append(
        f"- Redis {s.redis_version}, role {s.role}, uptime {human_duration(s.uptime_seconds)}"
    )
    if s.maxmemory_bytes:
        pct = 100 * s.used_memory_bytes / s.maxmemory_bytes
        out.append(
            f"- Memory: {human_bytes(s.used_memory_bytes)} / "
            f"{human_bytes(s.maxmemory_bytes)} ({pct:.0f}%)"
        )
    else:
        out.append(f"- Memory: {human_bytes(s.used_memory_bytes)} / unbounded")
    out.append(f"- Clients: {s.connected_clients} connected, {s.blocked_clients} blocked")
    out.append(f"- Eviction policy: {s.maxmemory_policy}")
    if report.sampled:
        out.append(f"- Keys: {s.total_keys:,} (sampled)")
    else:
        out.append(f"- Keys: {s.total_keys:,}")
    out.append("")

    for severity in _SEVERITY_ORDER:
        group = [f for f in report.findings if f.severity == severity]
        if not group:
            continue
        out.append(f"## {_SEVERITY_HEADING[severity]}")
        out.append("")
        for f in group:
            out.append(f"### [{f.category.value}] {f.id}")
            out.append("")
            out.append(f"**{f.title}**")
            out.append("")
            if f.explanation:
                out.append(f.explanation)
                out.append("")
            if f.evidence:
                out.append("Evidence:")
                out.append("")
                out.append("```json")
                out.append(_fmt_evidence(f.evidence))
                out.append("```")
                out.append("")
            if f.suggested_checks:
                out.append("Checks:")
                out.extend(f"- `{c}`" for c in f.suggested_checks)
                out.append("")
            if f.suggested_fixes:
                out.append("Fixes:")
                out.extend(f"- {x}" for x in f.suggested_fixes)
                out.append("")

    if report.skipped:
        out.append("## Skipped modules")
        out.append("")
        for sk in report.skipped:
            out.append(f"- **{sk.module}**: {sk.reason}")
        out.append("")

    out.append("## Raw stats")
    out.append("")
    out.append("```json")
    out.append(_fmt_evidence(report.stats))
    out.append("```")
    out.append("")
    return "\n".join(out)


def _fmt_evidence(data) -> str:
    import json

    return json.dumps(data, indent=2, default=str)
