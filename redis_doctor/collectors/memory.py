"""Memory collector — INFO memory fields, plus MEMORY STATS when permitted."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.server import MemoryStats
from .base import Collector

if TYPE_CHECKING:
    from ..pipeline import RunContext


def _int(d: dict, key: str, default: int = 0) -> int:
    try:
        return int(d.get(key, default))
    except (ValueError, TypeError):
        return default


def _float(d: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(d.get(key, default))
    except (ValueError, TypeError):
        return default


class MemoryCollector(Collector):
    name = "memory"

    def collect(self, ctx: RunContext) -> MemoryStats:
        f = ctx.info_fields()
        stats = MemoryStats(
            used_memory=_int(f, "used_memory"),
            used_memory_peak=_int(f, "used_memory_peak"),
            used_memory_rss=_int(f, "used_memory_rss"),
            maxmemory=_int(f, "maxmemory"),
            maxmemory_policy=f.get("maxmemory_policy", "noeviction"),
            mem_fragmentation_ratio=_float(f, "mem_fragmentation_ratio"),
            allocator_frag_ratio=_float(f, "allocator_frag_ratio"),
            allocator_rss_ratio=_float(f, "allocator_rss_ratio"),
        )
        return stats
