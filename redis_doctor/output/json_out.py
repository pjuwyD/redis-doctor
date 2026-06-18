"""JSON output — the full Report model serialized. Stable automation contract."""

from __future__ import annotations

from ..models.report import Report


def render_json(report: Report) -> str:
    return report.model_dump_json(indent=2)
