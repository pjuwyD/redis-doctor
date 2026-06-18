"""Slack incoming-webhook notifier."""

from __future__ import annotations

import json
import urllib.request

from ..models.report import Report


def build_payload(report: Report) -> dict:
    lines = [
        f"*Redis Doctor* — {report.target}",
        f"Health score: *{report.health_score}/100*",
        f"{report.summary.critical} critical, {report.summary.warning} warning, "
        f"{report.summary.info} info",
    ]
    for f in report.findings[:10]:
        if f.severity.value in ("critical", "warning"):
            lines.append(f"• [{f.severity.value}] {f.title}")
    return {"text": "\n".join(lines)}


def send(webhook_url: str, report: Report, *, _opener=urllib.request.urlopen) -> None:
    data = json.dumps(build_payload(report)).encode()
    req = urllib.request.Request(
        webhook_url, data=data, headers={"Content-Type": "application/json"}
    )
    _opener(req, timeout=10)
