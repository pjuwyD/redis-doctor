"""The shared at-a-glance overview + client-state breakdown."""

from __future__ import annotations

import pytest

from redis_doctor.config import Config
from redis_doctor.models.client import ClientInfo
from redis_doctor.output.terminal import overview_table
from redis_doctor.pipeline import _build_overview, client_states


def test_client_states_classification():
    clients = [
        ClientInfo(addr="1:1", flags="N", idle_seconds=0),  # active
        ClientInfo(addr="1:2", flags="N", idle_seconds=120),  # idle
        ClientInfo(addr="1:3", flags="b", idle_seconds=0),  # blocked
        ClientInfo(addr="1:4", flags="O", idle_seconds=0),  # monitor
        ClientInfo(addr="1:5", flags="S", idle_seconds=0),  # replica link
        ClientInfo(addr="1:6", flags="c", idle_seconds=0),  # closing
        ClientInfo(addr="1:7", flags="P", idle_seconds=0),  # pubsub
        ClientInfo(addr="1:8", flags="N", idle_seconds=0, output_buffer=5 * 1024 * 1024),  # slow
    ]
    states = client_states(clients)
    assert states["active"] == 1
    assert states["idle"] == 1
    assert states["blocked"] == 1
    assert states["monitor"] == 1
    assert states["replica_link"] == 1
    assert states["closing"] == 1
    assert states["pubsub"] == 1
    assert states["slow_consumer"] == 1


@pytest.fixture
def ctx(safe_fake):
    from redis_doctor.pipeline import RunContext

    return RunContext(redis=safe_fake, config=Config())


def test_build_overview_aggregates(ctx):
    from redis_doctor.collectors.keyspace import KeyspaceData
    from redis_doctor.models.sample import KeySample
    from redis_doctor.models.server import ServerInfo
    from redis_doctor.models.stream import StreamGroup, StreamInfo

    info = ServerInfo(
        redis_version="7.4.7",
        connected_clients=10,
        blocked_clients=2,
        maxclients=100,
        used_memory_bytes=1000,
        keyspace_hits=90,
        keyspace_misses=10,
        instantaneous_ops_per_sec=42,
    )
    ctx.collected["info"] = info
    ctx.collected["keyspace"] = KeyspaceData(
        sample=KeySample(scanned=5, complete=True),
        dbsize=123,
        type_distribution={"string": 100, "hash": 23},
    )
    ctx.collected["streams"] = [
        StreamInfo(name="s", length=10, groups=[StreamGroup(name="g", pending=7)])
    ]
    ctx.collected["scripting"] = {"cached_scripts": 5, "functions_count": 8, "libraries_count": 8}
    ctx.collected["clients"] = [ClientInfo(addr="1:1", flags="N", name="svc")]

    ov = _build_overview(ctx, info)
    assert ov["keys"]["total"] == 123
    assert ov["keys"]["by_type"]["string"] == 100
    assert ov["streams"] == {"count": 1, "total_pending": 7}
    assert ov["scripting"]["functions"] == 8
    assert ov["clients"]["total"] == 1 and ov["clients"]["states"]["active"] == 1
    assert ov["server"]["hit_rate"] == 90.0
    assert ov["server"]["ops_per_sec"] == 42


def test_overview_table_handles_empty():
    assert overview_table(None) is None
    assert overview_table({}) is None


def test_overview_table_renders():
    table = overview_table(
        {
            "keys": {"total": 100, "sampled": 100, "complete": True, "by_type": {"string": 100}},
            "clients": {"total": 5, "blocked": 0, "states": {"active": 5}},
            "memory": {"used_bytes": 1000, "max_bytes": 0, "policy": "noeviction", "pct": None},
            "server": {"ops_per_sec": 10, "hit_rate": 99.0, "evicted_keys": 0},
        }
    )
    assert table is not None  # builds without error
