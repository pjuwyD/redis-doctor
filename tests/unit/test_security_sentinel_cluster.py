"""Security, Sentinel, and Cluster analyzers."""

from __future__ import annotations

import pytest

from redis_doctor.analyzers.cluster_rules import analyze_cluster
from redis_doctor.analyzers.security_rules import SecurityAnalyzer
from redis_doctor.analyzers.sentinel_rules import analyze_sentinel
from redis_doctor.collectors.cluster import ClusterData, ClusterNode, _parse_nodes
from redis_doctor.collectors.security import redact_acl_line
from redis_doctor.collectors.sentinel import SentinelReplica, SentinelTopology
from redis_doctor.config import Config
from redis_doctor.models.finding import Severity


@pytest.fixture
def ctx(safe_fake):
    from redis_doctor.pipeline import RunContext

    return RunContext(redis=safe_fake, config=Config())


def _ids(findings):
    return {f.id: f for f in findings}


# --- security -------------------------------------------------------------


def test_security_no_auth_and_protected_mode(ctx):
    ctx.collected["security"] = {
        "requirepass_set": False,
        "protected_mode": "no",
        "acl_list": ["user default on nopass ~* &* +@all"],
        "total_clients": 1,
        "default_user_clients": 1,
    }
    f = _ids(SecurityAnalyzer().analyze(ctx))
    assert f["security.no_auth"].severity == Severity.CRITICAL
    assert "security.protected_mode_off" in f
    assert "security.default_user" in f


def test_security_with_auth_no_finding(ctx):
    ctx.collected["security"] = {
        "requirepass_set": True,
        "protected_mode": "yes",
        "acl_list": ["user default on #abc ~* &* +@all"],
        "total_clients": 1,
        "default_user_clients": 0,
    }
    f = _ids(SecurityAnalyzer().analyze(ctx))
    assert "security.no_auth" not in f
    assert "security.protected_mode_off" not in f


def test_acl_redaction():
    line = "user app on >mypassword123 #deadbeefhash ~* +@all"
    redacted = redact_acl_line(line)
    assert "mypassword123" not in redacted
    assert "deadbeefhash" not in redacted
    assert ">***" in redacted
    assert "#***" in redacted


# --- sentinel -------------------------------------------------------------


def test_sentinel_insufficient_quorum():
    topo = SentinelTopology(master_name="m", quorum=2, reachable_sentinels=1)
    f = _ids(analyze_sentinel(topo, Config()))
    assert f["sentinel.insufficient_quorum"].severity == Severity.CRITICAL


def test_sentinel_master_disagreement_and_lag():
    topo = SentinelTopology(
        master_name="m",
        quorum=1,
        reachable_sentinels=2,
        master_addrs={"10.0.0.1:6379", "10.0.0.2:6379"},
        replicas=[SentinelReplica(addr="10.0.0.3:6379", lag_seconds=200, reachable=True)],
    )
    f = _ids(analyze_sentinel(topo, Config()))
    assert "sentinel.master_disagreement" in f
    assert f["sentinel.replica_lag_high"].severity == Severity.CRITICAL


def test_sentinel_unreachable_replica_and_failover_timeout():
    topo = SentinelTopology(
        master_name="m",
        quorum=1,
        reachable_sentinels=1,
        failover_timeout_ms=180000,
        replicas=[SentinelReplica(addr="r:6379", flags="slave,s_down", reachable=False)],
    )
    f = _ids(analyze_sentinel(topo, Config()))
    assert "sentinel.unreachable_replica" in f
    assert "sentinel.failover_timeout_unusual" in f


# --- cluster --------------------------------------------------------------


def test_cluster_parse_nodes():
    raw = (
        "abc 127.0.0.1:7000@17000 myself,master - 0 0 1 connected 0-5460\n"
        "def 127.0.0.1:7001@17001 master - 0 0 2 connected 5461-10922\n"
        "ghi 127.0.0.1:7002@17002 slave abc 0 0 1 connected\n"
    )
    nodes = _parse_nodes(raw)
    assert len(nodes) == 3
    masters = [n for n in nodes if n.role == "master"]
    assert len(masters) == 2
    assert masters[0].slots == 5461


def test_cluster_uncovered_and_failed():
    data = ClusterData(
        enabled=True,
        state="fail",
        slots_assigned=10000,
        nodes=[
            ClusterNode(id="a", addr="10.0.0.1:7000", role="master", failed=True),
        ],
    )
    f = _ids(analyze_cluster(data))
    assert f["cluster.uncovered_slots"].severity == Severity.CRITICAL
    assert f["cluster.failed_node"].severity == Severity.CRITICAL


def test_cluster_master_without_replica_and_uneven():
    data = ClusterData(
        enabled=True,
        state="ok",
        slots_assigned=16384,
        nodes=[
            ClusterNode(id="a", addr="n1", role="master", keys=100, used_memory=1000),
            ClusterNode(id="b", addr="n2", role="master", keys=1000, used_memory=50000),
        ],
    )
    f = _ids(analyze_cluster(data))
    assert "cluster.master_without_replica" in f
    assert "cluster.uneven_keys" in f
    assert "cluster.uneven_memory" in f


def test_cluster_not_enabled_no_findings():
    assert analyze_cluster(ClusterData(enabled=False)) == []
