"""Latency collector — LATENCY LATEST and LATENCY DOCTOR."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import Collector

if TYPE_CHECKING:
    from ..pipeline import RunContext


class LatencyData:
    """Parsed latency events: list of {event, timestamp, latest_ms, max_ms}."""

    def __init__(self, events: list[dict[str, Any]], doctor: str = ""):
        self.events = events
        self.doctor = doctor


class LatencyCollector(Collector):
    name = "latency"

    def collect(self, ctx: RunContext) -> LatencyData:
        raw = ctx.redis.execute("LATENCY", "LATEST") or []
        events: list[dict[str, Any]] = []
        for row in raw:
            # [event, timestamp, latest_ms, max_ms]
            if not isinstance(row, (list, tuple)) or len(row) < 4:
                continue
            events.append(
                {
                    "event": str(row[0]),
                    "timestamp": int(row[1]),
                    "latest_ms": int(row[2]),
                    "max_ms": int(row[3]),
                }
            )
        try:
            doctor = ctx.redis.execute("LATENCY", "DOCTOR") or ""
        except Exception:
            doctor = ""
        return LatencyData(events, str(doctor))
