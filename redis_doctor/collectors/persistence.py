"""Persistence collector — INFO persistence fields."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import Collector

if TYPE_CHECKING:
    from ..pipeline import RunContext

_FIELDS = [
    "loading",
    "rdb_changes_since_last_save",
    "rdb_bgsave_in_progress",
    "rdb_last_save_time",
    "rdb_last_bgsave_status",
    "aof_enabled",
    "aof_last_bgrewrite_status",
    "aof_last_write_status",
    "aof_rewrite_in_progress",
]


class PersistenceCollector(Collector):
    name = "persistence"

    def collect(self, ctx: RunContext) -> dict[str, Any]:
        f = ctx.info_fields()
        return {k: f.get(k) for k in _FIELDS if k in f}
