"""Email (SMTP) notifier.

Config is the destination address; SMTP host/port come from env
(REDIS_DOCTOR_SMTP_HOST, _PORT, _FROM), defaulting to localhost:25.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from ..models.report import Report
from ..output.markdown import render_markdown


def build_message(to_addr: str, report: Report) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = (
        f"Redis Doctor: {report.target} scored {report.health_score}/100 "
        f"({report.summary.critical} critical)"
    )
    msg["From"] = os.environ.get("REDIS_DOCTOR_SMTP_FROM", "redis-doctor@localhost")
    msg["To"] = to_addr
    msg.set_content(render_markdown(report))
    return msg


def send(to_addr: str, report: Report, *, _smtp=smtplib.SMTP) -> None:
    host = os.environ.get("REDIS_DOCTOR_SMTP_HOST", "localhost")
    port = int(os.environ.get("REDIS_DOCTOR_SMTP_PORT", "25"))
    msg = build_message(to_addr, report)
    with _smtp(host, port, timeout=10) as smtp:
        smtp.send_message(msg)
