"""Finding-ID assertions for the memory, latency, config, persistence and
replication analyzers, against synthetic collected data."""

from __future__ import annotations

import time

import pytest

from redis_doctor.analyzers.config_rules import ConfigAnalyzer
from redis_doctor.analyzers.latency_rules import LatencyAnalyzer
from redis_doctor.analyzers.memory_rules import MemoryAnalyzer
from redis_doctor.analyzers.persistence_rules import PersistenceAnalyzer
from redis_doctor.analyzers.replication_rules import ReplicationAnalyzer
from redis_doctor.collectors.latency import LatencyData
from redis_doctor.collectors.replication import ReplicationData
from redis_doctor.config import Config
from redis_doctor.models.client import ClientInfo
from redis_doctor.models.finding import Severity
from redis_doctor.models.server import MemoryStats


@pytest.fixture
def ctx(safe_fake):
    from redis_doctor.pipeline import RunContext

    return RunContext(redis=safe_fake, config=Config())


def _by_id(findings):
    return {f.id: f for f in findings}


def test_memory_high_usage_noeviction_critical(ctx):
    ctx.collected["memory"] = MemoryStats(
        used_memory=95, maxmemory=100, maxmemory_policy="noeviction"
    )
    findings = _by_id(MemoryAnalyzer().analyze(ctx))
    assert "memory.high_usage_noeviction" in findings
    assert findings["memory.high_usage_noeviction"].severity == Severity.CRITICAL
    assert findings["memory.high_usage"].severity == Severity.CRITICAL


def test_memory_no_maxmemory(ctx):
    ctx.collected["memory"] = MemoryStats(used_memory=1000, maxmemory=0)
    findings = _by_id(MemoryAnalyzer().analyze(ctx))
    assert "memory.no_maxmemory" in findings
    assert "memory.high_usage_noeviction" not in findings


def test_memory_warning_band(ctx):
    ctx.collected["memory"] = MemoryStats(
        used_memory=82, maxmemory=100, maxmemory_policy="allkeys-lru"
    )
    findings = _by_id(MemoryAnalyzer().analyze(ctx))
    assert findings["memory.high_usage"].severity == Severity.WARNING
    assert "memory.high_usage_noeviction" not in findings


def test_config_timeout_zero_with_idle(ctx):
    ctx.config.thresholds.idle_client_warning_seconds = 10
    ctx.config.thresholds.idle_client_warning_count = 2
    ctx.collected["config_values"] = {"timeout": "0", "maxmemory": "100", "save": "3600 1"}
    ctx.collected["clients"] = [
        ClientInfo(addr="1.1.1.1:1", idle_seconds=100),
        ClientInfo(addr="1.1.1.1:2", idle_seconds=100),
        ClientInfo(addr="1.1.1.1:3", idle_seconds=0),
    ]
    findings = _by_id(ConfigAnalyzer().analyze(ctx))
    assert "config.timeout_zero_with_idle" in findings


def test_persistence_rdb_failed_critical(ctx):
    ctx.collected["persistence"] = {"rdb_last_bgsave_status": "err"}
    findings = _by_id(PersistenceAnalyzer().analyze(ctx))
    assert findings["persistence.rdb_failed"].severity == Severity.CRITICAL


def test_persistence_aof_and_loading(ctx):
    ctx.collected["persistence"] = {
        "aof_last_write_status": "err",
        "loading": "1",
    }
    findings = _by_id(PersistenceAnalyzer().analyze(ctx))
    assert "persistence.aof_failed" in findings
    assert "persistence.loading" in findings


def test_persistence_last_save_old(ctx):
    ctx.collected["persistence"] = {
        "rdb_changes_since_last_save": "50000",
        "rdb_last_save_time": str(int(time.time()) - 7200),
    }
    findings = _by_id(PersistenceAnalyzer().analyze(ctx))
    assert "persistence.last_save_old" in findings


def test_replication_lag_high_critical(ctx):
    ctx.collected["replication"] = ReplicationData(
        {
            "role": "slave",
            "master_host": "10.0.0.1",
            "master_link_status": "up",
            "master_last_io_seconds_ago": "130",
            "slave_read_only": "1",
        }
    )
    findings = _by_id(ReplicationAnalyzer().analyze(ctx))
    assert findings["replication.lag_high"].severity == Severity.CRITICAL


def test_replication_link_down_and_writable(ctx):
    ctx.collected["replication"] = ReplicationData(
        {
            "role": "slave",
            "master_link_status": "down",
            "master_last_io_seconds_ago": "5",
            "slave_read_only": "0",
        }
    )
    findings = _by_id(ReplicationAnalyzer().analyze(ctx))
    assert "replication.link_down" in findings
    assert "replication.replica_writable" in findings


def test_replication_master_slave_lag(ctx):
    ctx.collected["replication"] = ReplicationData(
        {
            "role": "master",
            "connected_slaves": "1",
            "slave0": {"ip": "10.0.0.2", "port": "6379", "state": "online", "lag": "200"},
        }
    )
    findings = _by_id(ReplicationAnalyzer().analyze(ctx))
    assert findings["replication.lag_high"].severity == Severity.CRITICAL


def test_latency_spike_and_fork(ctx):
    ctx.collected["latency"] = LatencyData(
        events=[
            {"event": "command", "timestamp": 1, "latest_ms": 50, "max_ms": 250},
            {"event": "fork", "timestamp": 1, "latest_ms": 120, "max_ms": 300},
        ]
    )
    findings = _by_id(LatencyAnalyzer().analyze(ctx))
    assert "latency.spike" in findings
    assert "latency.fork_slow" in findings
