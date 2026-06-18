"""Slowlog collector (Section 9.9). SLOWLOG LEN + SLOWLOG GET."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models.slowlog import SlowlogEntry
from .base import Collector

if TYPE_CHECKING:
    from ..pipeline import RunContext

# Commands whose arguments are secrets and must be fully redacted.
_SECRET_COMMANDS = {"AUTH", "HELLO"}
# A token that looks like a credential (long, high-entropy).
_SECRETISH = re.compile(r"^[A-Za-z0-9+/=_\-]{32,}$")


def _s(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value) if value is not None else ""


def _command_tokens(raw) -> list[str]:
    if isinstance(raw, (list, tuple)):
        return [_s(t) for t in raw]
    return _s(raw).split()


def redact_args(command: str, args: list[str]) -> list[str]:
    if command.upper() in _SECRET_COMMANDS:
        return ["***" for _ in args]
    return ["***" if _SECRETISH.match(a) else a for a in args]


class SlowlogCollector(Collector):
    name = "slowlog"

    def collect(self, ctx: RunContext) -> dict:
        length = int(ctx.redis.execute("SLOWLOG", "LEN") or 0)
        limit = ctx.config.thresholds.slowlog_max_entries
        raw_entries = ctx.redis.execute("SLOWLOG", "GET", limit) or []

        entries: list[SlowlogEntry] = []
        for e in raw_entries:
            if isinstance(e, dict):
                eid = e.get("id", 0)
                ts = e.get("start_time", 0)
                dur = e.get("duration", 0)
                tokens = _command_tokens(e.get("command", ""))
            elif isinstance(e, (list, tuple)) and len(e) >= 4:
                eid, ts, dur, cmd = e[0], e[1], e[2], e[3]
                tokens = _command_tokens(cmd)
            else:
                continue
            command = tokens[0].upper() if tokens else ""
            args = redact_args(command, tokens[1:])
            entries.append(
                SlowlogEntry(
                    id=int(eid or 0),
                    timestamp=int(ts or 0),
                    duration_us=int(dur or 0),
                    command=command,
                    args=args,
                )
            )

        return {"length": length, "entries": entries}
