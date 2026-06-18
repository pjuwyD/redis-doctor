"""Sentinel collector (Section 9.15).

Connects to one or more Sentinel nodes using read-only SENTINEL subcommands and
builds a normalized topology for the analyzer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import redis

from ..connection import SafeRedis, parse_target
from ..errors import ConnectionError as RDConnectionError


def _s(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value) if value is not None else ""


def _i(d: dict, key: str, default: int = 0) -> int:
    try:
        return int(d.get(key, default))
    except (ValueError, TypeError):
        return default


@dataclass
class SentinelReplica:
    addr: str
    flags: str = ""
    lag_seconds: int = 0
    reachable: bool = True


@dataclass
class SentinelTopology:
    master_name: str
    quorum: int = 0
    reachable_sentinels: int = 0
    configured_sentinels: int = 0
    failover_timeout_ms: int = 0
    down_after_ms: int = 0
    master_addrs: set[str] = field(default_factory=set)
    replicas: list[SentinelReplica] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _connect(node: str, password: str | None) -> SafeRedis:
    host, _, port = node.partition(":")
    target = parse_target(host=host, port=int(port or 26379), password=password)
    return SafeRedis(
        redis.Redis(
            host=target.host,
            port=target.port,
            password=password,
            socket_timeout=5,
            socket_connect_timeout=5,
            decode_responses=True,
        ),
        target,
    )


def collect_sentinel(
    nodes: list[str],
    master_name: str,
    sentinel_password: str | None = None,
) -> SentinelTopology:
    topo = SentinelTopology(master_name=master_name)
    if not nodes:
        raise RDConnectionError("at least one --sentinel-node is required")

    num_other = 0
    for node in nodes:
        try:
            sr = _connect(node, sentinel_password)
            sr.ping()
        except Exception as e:
            topo.errors.append(f"sentinel {node} unreachable: {e}")
            continue
        topo.reachable_sentinels += 1
        try:
            master = sr.execute("SENTINEL", "MASTER", master_name) or {}
            master = {_s(k): _s(v) for k, v in master.items()} if isinstance(master, dict) else {}
            topo.quorum = _i(master, "quorum", topo.quorum)
            topo.failover_timeout_ms = _i(master, "failover-timeout", topo.failover_timeout_ms)
            topo.down_after_ms = _i(master, "down-after-milliseconds", topo.down_after_ms)
            num_other = max(num_other, _i(master, "num-other-sentinels"))

            addr = sr.execute("SENTINEL", "GET-MASTER-ADDR-BY-NAME", master_name)
            if isinstance(addr, (list, tuple)) and len(addr) >= 2:
                topo.master_addrs.add(f"{_s(addr[0])}:{_s(addr[1])}")

            _collect_replicas(sr, master_name, topo)
        except Exception as e:
            topo.errors.append(f"sentinel {node} query failed: {e}")
        finally:
            sr.close()

    topo.configured_sentinels = topo.reachable_sentinels + num_other
    return topo


def _collect_replicas(sr: SafeRedis, master_name: str, topo: SentinelTopology) -> None:
    if topo.replicas:
        return  # one sentinel's view is enough for the replica list
    try:
        replicas = sr.execute("SENTINEL", "REPLICAS", master_name) or []
    except redis.ResponseError:
        replicas = sr.execute("SENTINEL", "SLAVES", master_name) or []
    for r in replicas:
        rd: dict[str, Any] = {_s(k): _s(v) for k, v in r.items()} if isinstance(r, dict) else {}
        flags = rd.get("flags", "")
        down_ms = _i(rd, "master-link-down-time")
        reachable = not any(f in flags for f in ("s_down", "o_down", "disconnected"))
        topo.replicas.append(
            SentinelReplica(
                addr=f"{rd.get('ip', '?')}:{rd.get('port', '?')}",
                flags=flags,
                lag_seconds=down_ms // 1000,
                reachable=reachable,
            )
        )
