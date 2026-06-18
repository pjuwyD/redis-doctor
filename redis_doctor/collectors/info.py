"""INFO collector — parses all INFO sections into ServerInfo."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.server import ServerInfo
from .base import Collector

if TYPE_CHECKING:
    from ..pipeline import RunContext


def parse_info(raw: str) -> dict[str, str]:
    """Parse the raw INFO text reply into a flat {field: value} dict."""
    out: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def _int(d: dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(d.get(key, default))
    except (ValueError, TypeError):
        return default


def _float(d: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(d.get(key, default))
    except (ValueError, TypeError):
        return default


def _parse_keyspace(d: dict) -> dict[str, dict[str, int]]:
    """db0:keys=12,expires=3,avg_ttl=0 -> {'db0': {'keys': 12, 'expires': 3}}.

    Handles both the raw INFO string form and the dict redis-py already parses
    (where each ``dbN`` value is itself a dict).
    """
    ks: dict[str, dict[str, int]] = {}
    for key, value in d.items():
        if not key.startswith("db"):
            continue
        if isinstance(value, dict):
            ks[key] = {k: int(v) for k, v in value.items() if str(v).lstrip("-").isdigit()}
            continue
        if not isinstance(value, str) or "keys=" not in value:
            continue
        parts: dict[str, int] = {}
        for token in value.split(","):
            k, _, v = token.partition("=")
            try:
                parts[k.strip()] = int(v)
            except ValueError:
                continue
        ks[key] = parts
    return ks


def build_server_info(fields: dict) -> ServerInfo:
    keyspace = _parse_keyspace(fields)
    total_keys = sum(db.get("keys", 0) for db in keyspace.values())
    return ServerInfo(
        redis_version=fields.get("redis_version", "unknown"),
        redis_mode=fields.get("redis_mode", "standalone"),
        uptime_seconds=_int(fields, "uptime_in_seconds"),
        role=fields.get("role", "master"),
        connected_clients=_int(fields, "connected_clients"),
        blocked_clients=_int(fields, "blocked_clients"),
        maxclients=_int(fields, "maxclients"),
        used_memory_bytes=_int(fields, "used_memory"),
        used_memory_rss_bytes=_int(fields, "used_memory_rss"),
        used_memory_peak_bytes=_int(fields, "used_memory_peak"),
        maxmemory_bytes=_int(fields, "maxmemory"),
        maxmemory_policy=fields.get("maxmemory_policy", "noeviction"),
        total_keys=total_keys,
        expired_keys=_int(fields, "expired_keys"),
        evicted_keys=_int(fields, "evicted_keys"),
        instantaneous_ops_per_sec=_int(fields, "instantaneous_ops_per_sec"),
        keyspace_hits=_int(fields, "keyspace_hits"),
        keyspace_misses=_int(fields, "keyspace_misses"),
        mem_fragmentation_ratio=_float(fields, "mem_fragmentation_ratio"),
        rdb_last_bgsave_status=fields.get("rdb_last_bgsave_status", "ok"),
        aof_enabled=_int(fields, "aof_enabled") == 1,
        connected_slaves=_int(fields, "connected_slaves"),
        keyspace=keyspace,
    )


class InfoCollector(Collector):
    name = "info"

    def collect(self, ctx: RunContext) -> ServerInfo:
        raw = ctx.redis.execute("INFO", "all")
        # redis-py parses INFO into a dict; fakeredis/raw paths may return a string.
        fields = parse_info(raw) if isinstance(raw, str) else dict(raw)
        info = build_server_info(fields)
        ctx.raw_info = fields
        return info
