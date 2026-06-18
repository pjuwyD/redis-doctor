"""ServerInfo and MemoryStats — parsed INFO fields."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ServerInfo(BaseModel):
    redis_version: str = "unknown"
    redis_mode: str = "standalone"
    uptime_seconds: int = 0
    role: str = "master"
    connected_clients: int = 0
    blocked_clients: int = 0
    maxclients: int = 0
    used_memory_bytes: int = 0
    used_memory_rss_bytes: int = 0
    used_memory_peak_bytes: int = 0
    maxmemory_bytes: int = 0
    maxmemory_policy: str = "noeviction"
    total_keys: int = 0
    expired_keys: int = 0
    evicted_keys: int = 0
    instantaneous_ops_per_sec: int = 0
    keyspace_hits: int = 0
    keyspace_misses: int = 0
    mem_fragmentation_ratio: float = 0.0
    rdb_last_bgsave_status: str = "ok"
    aof_enabled: bool = False
    connected_slaves: int = 0
    # Per-DB keyspace, e.g. {"db0": {"keys": 12, "expires": 3}}
    keyspace: dict[str, dict[str, int]] = Field(default_factory=dict)


class MemoryStats(BaseModel):
    used_memory: int = 0
    used_memory_peak: int = 0
    used_memory_rss: int = 0
    maxmemory: int = 0
    maxmemory_policy: str = "noeviction"
    mem_fragmentation_ratio: float = 0.0
    allocator_frag_ratio: float = 0.0
    allocator_rss_ratio: float = 0.0
