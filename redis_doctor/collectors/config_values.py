"""Config collector — CONFIG GET for the selected risk-relevant keys."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Collector

if TYPE_CHECKING:
    from ..pipeline import RunContext

CONFIG_KEYS = [
    "maxmemory",
    "maxmemory-policy",
    "maxclients",
    "timeout",
    "tcp-keepalive",
    "appendonly",
    "save",
    "slowlog-log-slower-than",
    "slowlog-max-len",
    "client-output-buffer-limit",
    "notify-keyspace-events",
    "requirepass",
    "protected-mode",
]


class ConfigValuesCollector(Collector):
    name = "config_values"

    def collect(self, ctx: RunContext) -> dict[str, str]:
        values: dict[str, str] = {}
        for key in CONFIG_KEYS:
            res = ctx.redis.execute("CONFIG", "GET", key)
            # CONFIG GET returns [key, value] or a dict depending on client parsing.
            if isinstance(res, dict):
                values.update({str(k): str(v) for k, v in res.items()})
            elif isinstance(res, (list, tuple)) and len(res) >= 2:
                values[str(res[0])] = str(res[1])
        return values
