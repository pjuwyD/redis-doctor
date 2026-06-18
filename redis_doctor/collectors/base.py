"""Collector ABC with timeout + graceful-skip handling.

A collector READS data from Redis and returns raw model objects. If a required
command is denied (ACL) or unsupported, the collector records a SkippedModule
and returns None instead of crashing the run (Section 0 rule 6, Section 14).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import redis

from ..logging import get_logger
from ..models.report import SkippedModule

if TYPE_CHECKING:
    from ..pipeline import RunContext

log = get_logger()


class Collector(ABC):
    name: str = "collector"

    @abstractmethod
    def collect(self, ctx: RunContext) -> Any:
        """Read from Redis and return a model object (or None if skipped)."""

    def run(self, ctx: RunContext) -> Any:
        """Execute collect() with skip handling. Never raises for Redis errors."""
        try:
            return self.collect(ctx)
        except redis.ResponseError as e:
            reason = _permission_reason(str(e), self.name)
            ctx.skip(self.name, reason)
            log.warning("collector %s skipped: %s", self.name, reason)
            return None
        except (redis.TimeoutError, redis.ConnectionError) as e:
            ctx.skip(self.name, f"redis error: {e}")
            log.warning("collector %s skipped: %s", self.name, e)
            return None


def _permission_reason(message: str, name: str) -> str:
    low = message.lower()
    if "noperm" in low or "permission" in low or "no permissions" in low:
        return f"user lacks permission for {name}"
    if "unknown command" in low:
        return f"command unavailable for {name}"
    return f"{name} unavailable: {message}"


def record_skip(skipped: list[SkippedModule], module: str, reason: str) -> None:
    skipped.append(SkippedModule(module=module, reason=reason))
