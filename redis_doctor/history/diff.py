"""Report diffing (Section 13.2).

Findings are matched by (id, primary affected key). Also computes health-score
and per-category deltas, plus key metric deltas (memory, keys, prefixes, streams,
idle clients).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..models.report import Report


class FindingRef(BaseModel):
    id: str
    affected: str = ""
    severity: str = ""
    title: str = ""


class Diff(BaseModel):
    added: list[FindingRef] = Field(default_factory=list)
    removed: list[FindingRef] = Field(default_factory=list)
    unchanged: list[FindingRef] = Field(default_factory=list)
    score_before: int = 0
    score_after: int = 0
    score_delta: int = 0
    category_deltas: dict[str, int] = Field(default_factory=dict)
    metric_deltas: dict[str, Any] = Field(default_factory=dict)


def _key(f) -> tuple[str, str]:
    return (f.id, f.affected[0] if f.affected else "")


def _ref(f) -> FindingRef:
    return FindingRef(
        id=f.id,
        affected=f.affected[0] if f.affected else "",
        severity=f.severity.value if hasattr(f.severity, "value") else str(f.severity),
        title=f.title,
    )


def _prefix_counts(report: Report) -> dict[str, int]:
    ks = report.stats.get("keyspace") or {}
    return {p["prefix"]: p["count"] for p in ks.get("top_prefixes_by_count", [])}


def _stream_lengths(report: Report) -> dict[str, int]:
    return {st["name"]: st["length"] for st in (report.stats.get("streams") or [])}


def _idle_clients(report: Report) -> int:
    return (report.stats.get("clients") or {}).get("idle_over_1h", 0)


def diff_reports(before: Report, after: Report) -> Diff:
    before_map = {_key(f): f for f in before.findings}
    after_map = {_key(f): f for f in after.findings}

    added = [_ref(f) for k, f in after_map.items() if k not in before_map]
    removed = [_ref(f) for k, f in before_map.items() if k not in after_map]
    unchanged = [_ref(f) for k, f in after_map.items() if k in before_map]

    cat_deltas: dict[str, int] = {}
    cats = set(before.category_scores) | set(after.category_scores)
    for c in cats:
        delta = after.category_scores.get(c, 100) - before.category_scores.get(c, 100)
        if delta:
            cat_deltas[c] = delta

    metric_deltas: dict[str, Any] = {
        "used_memory_bytes": {
            "before": before.server.used_memory_bytes,
            "after": after.server.used_memory_bytes,
            "delta": after.server.used_memory_bytes - before.server.used_memory_bytes,
        },
        "total_keys": {
            "before": before.server.total_keys,
            "after": after.server.total_keys,
            "delta": after.server.total_keys - before.server.total_keys,
        },
        "idle_clients": {
            "before": _idle_clients(before),
            "after": _idle_clients(after),
            "delta": _idle_clients(after) - _idle_clients(before),
        },
    }

    pb, pa = _prefix_counts(before), _prefix_counts(after)
    prefix_changes = {}
    for prefix in set(pb) | set(pa):
        d = pa.get(prefix, 0) - pb.get(prefix, 0)
        if d:
            prefix_changes[prefix] = d
    if prefix_changes:
        metric_deltas["prefix_count_changes"] = prefix_changes

    sb, sa = _stream_lengths(before), _stream_lengths(after)
    stream_changes = {}
    for name in set(sb) | set(sa):
        d = sa.get(name, 0) - sb.get(name, 0)
        if d:
            stream_changes[name] = d
    if stream_changes:
        metric_deltas["stream_length_changes"] = stream_changes

    return Diff(
        added=added,
        removed=removed,
        unchanged=unchanged,
        score_before=before.health_score,
        score_after=after.health_score,
        score_delta=after.health_score - before.health_score,
        category_deltas=cat_deltas,
        metric_deltas=metric_deltas,
    )


def render_diff_text(diff: Diff) -> str:
    out: list[str] = ["Since previous report:"]
    out.append(f"- health score {diff.score_before} -> {diff.score_after} ({diff.score_delta:+d})")
    mem = diff.metric_deltas.get("used_memory_bytes", {})
    if mem.get("delta"):
        before = mem["before"] or 1
        pct = 100 * mem["delta"] / before
        out.append(f"- memory changed by {pct:+.0f}% ({mem['delta']:+d} bytes)")
    keys = diff.metric_deltas.get("total_keys", {})
    if keys.get("delta"):
        out.append(f"- total keys changed by {keys['delta']:+d}")
    idle = diff.metric_deltas.get("idle_clients", {})
    if idle.get("delta"):
        out.append(f"- idle clients {idle['before']} -> {idle['after']}")
    for name, d in (diff.metric_deltas.get("stream_length_changes") or {}).items():
        out.append(f"- stream {name} grew by {d:+d} entries")
    for prefix, d in (diff.metric_deltas.get("prefix_count_changes") or {}).items():
        out.append(f"- prefix {prefix}:* changed by {d:+d} keys")
    if diff.added:
        out.append(f"- {len(diff.added)} new finding(s): " + ", ".join(f.id for f in diff.added))
    if diff.removed:
        out.append(
            f"- {len(diff.removed)} resolved finding(s): " + ", ".join(f.id for f in diff.removed)
        )
    return "\n".join(out)
