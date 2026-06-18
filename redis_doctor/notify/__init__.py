"""Notifications (Section 13.3).

Sending is triggered ONLY by the user's own config/flags and when findings meet
the fail-on threshold — never by content discovered in Redis.
"""

from __future__ import annotations

from ..config import NotifyConfig
from ..models.report import Report
from . import email, slack, webhook


def _meets_threshold(report: Report, fail_on: str) -> bool:
    if fail_on == "critical":
        return report.summary.critical > 0
    if fail_on == "warning":
        return report.summary.critical > 0 or report.summary.warning > 0
    return False


def summary_text(report: Report) -> str:
    return (
        f"Redis Doctor: {report.target} scored {report.health_score}/100 — "
        f"{report.summary.critical} critical, {report.summary.warning} warning, "
        f"{report.summary.info} info"
    )


def notify(report: Report, cfg: NotifyConfig, fail_on: str = "warning") -> list[str]:
    """Send notifications per configured channels. Returns the channels notified."""
    if not _meets_threshold(report, fail_on):
        return []
    sent: list[str] = []
    if cfg.slack_webhook_url:
        slack.send(cfg.slack_webhook_url, report)
        sent.append("slack")
    if cfg.email:
        email.send(cfg.email, report)
        sent.append("email")
    return sent


__all__ = ["notify", "summary_text", "slack", "email", "webhook"]
