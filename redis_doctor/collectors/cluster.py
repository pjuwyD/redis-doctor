"""Cluster collector (Section 9.16). Read-only CLUSTER subcommands."""

from __future__ import annotations

from dataclasses import dataclass, field

import redis

from ..connection import SafeRedis, parse_target

TOTAL_SLOTS = 16384


def _s(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value) if value is not None else ""


def _parse_cluster_info(raw) -> dict[str, str]:
    text = _s(raw) if not isinstance(raw, dict) else "\n".join(f"{k}:{v}" for k, v in raw.items())
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


@dataclass
class ClusterNode:
    id: str
    addr: str
    role: str = "master"
    master_id: str = "-"
    link_state: str = "connected"
    slots: int = 0
    failed: bool = False
    used_memory: int = 0
    keys: int = 0
    clients: int = 0
    reachable: bool = True


@dataclass
class ClusterData:
    enabled: bool = False
    state: str = "ok"
    slots_assigned: int = 0
    known_nodes: int = 0
    size: int = 0
    nodes: list[ClusterNode] = field(default_factory=list)

    @property
    def uncovered_slots(self) -> int:
        return max(0, TOTAL_SLOTS - self.slots_assigned)

    @property
    def masters(self) -> list[ClusterNode]:
        return [n for n in self.nodes if n.role == "master"]


def _parse_nodes(raw) -> list[ClusterNode]:
    nodes: list[ClusterNode] = []
    for line in _s(raw).splitlines():
        parts = line.split()
        if len(parts) < 8:
            continue
        node_id = parts[0]
        addr = parts[1].split("@")[0]
        flags = parts[2].split(",")
        master_id = parts[3]
        link_state = parts[7]
        slot_count = 0
        for tok in parts[8:]:
            if "-" in tok and not tok.startswith("["):
                lo, _, hi = tok.partition("-")
                try:
                    slot_count += int(hi) - int(lo) + 1
                except ValueError:
                    pass
            elif tok.isdigit():
                slot_count += 1
        nodes.append(
            ClusterNode(
                id=node_id,
                addr=addr,
                role="master" if "master" in flags else "slave",
                master_id=master_id,
                link_state=link_state,
                slots=slot_count,
                failed=any("fail" in f for f in flags),
            )
        )
    return nodes


def _enrich_node(node: ClusterNode, password: str | None) -> None:
    host, _, port = node.addr.partition(":")
    try:
        target = parse_target(host=host, port=int(port), password=password)
        client = redis.Redis(
            host=target.host,
            port=target.port,
            password=password,
            socket_timeout=3,
            socket_connect_timeout=3,
            decode_responses=True,
        )
        sr = SafeRedis(client, target)
        info = sr.execute("INFO", "all")
        from .info import parse_info

        fields = parse_info(info) if isinstance(info, str) else dict(info)
        node.used_memory = int(fields.get("used_memory", 0) or 0)
        node.clients = int(fields.get("connected_clients", 0) or 0)
        node.keys = int(sr.execute("DBSIZE") or 0)
        sr.close()
    except Exception:
        node.reachable = False


def collect_cluster(redis_conn: SafeRedis, password: str | None = None) -> ClusterData:
    data = ClusterData()
    fields = redis_conn.client.info("cluster") if hasattr(redis_conn.client, "info") else {}
    enabled = str(fields.get("cluster_enabled", 0)) in ("1", "True", "true")
    data.enabled = enabled
    if not enabled:
        return data

    info = _parse_cluster_info(redis_conn.execute("CLUSTER", "INFO"))
    data.state = info.get("cluster_state", "ok")
    data.slots_assigned = int(info.get("cluster_slots_assigned", 0) or 0)
    data.known_nodes = int(info.get("cluster_known_nodes", 0) or 0)
    data.size = int(info.get("cluster_size", 0) or 0)

    data.nodes = _parse_nodes(redis_conn.execute("CLUSTER", "NODES"))
    for node in data.nodes:
        if node.role == "master" and not node.failed:
            _enrich_node(node, password)
    return data
