"""Generic webhook notifier — POSTs the full Report JSON."""

from __future__ import annotations

import urllib.request

from ..models.report import Report


def send(url: str, report: Report, *, _opener=urllib.request.urlopen) -> None:
    data = report.model_dump_json().encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    _opener(req, timeout=10)
