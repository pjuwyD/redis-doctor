"""Replication collector — INFO replication fields (master and replica views)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import Collector

if TYPE_CHECKING:
    from ..pipeline import RunContext


def _parse_slave(value: Any) -> dict[str, Any]:
    """slaveN value: a dict (redis-py) or 'ip=..,port=..,state=..,offset=..,lag=..'."""
    if isinstance(value, dict):
        return dict(value)
    out: dict[str, Any] = {}
    if isinstance(value, str):
        for token in value.split(","):
            k, _, v = token.partition("=")
            out[k.strip()] = v.strip()
    return out


class ReplicationData:
    def __init__(self, fields: dict[str, Any]):
        self.role = str(fields.get("role", "master"))
        self.connected_slaves = _int(fields, "connected_slaves")
        self.master_repl_offset = _int(fields, "master_repl_offset")
        self.repl_backlog_size = _int(fields, "repl_backlog_size")
        # Replica view
        self.master_host = fields.get("master_host")
        self.master_link_status = fields.get("master_link_status")
        self.master_last_io_seconds_ago = _int(fields, "master_last_io_seconds_ago", -1)
        self.slave_repl_offset = _int(fields, "slave_repl_offset")
        self.slave_read_only = _int(fields, "slave_read_only", 1)
        # Per-slave entries
        self.slaves: list[dict[str, Any]] = []
        for key, value in fields.items():
            if key.startswith("slave") and key[5:].isdigit():
                self.slaves.append(_parse_slave(value))


def _int(d: dict, key: str, default: int = 0) -> int:
    try:
        return int(d.get(key, default))
    except (ValueError, TypeError):
        return default


class ReplicationCollector(Collector):
    name = "replication"

    def collect(self, ctx: RunContext) -> ReplicationData:
        return ReplicationData(ctx.info_fields())
