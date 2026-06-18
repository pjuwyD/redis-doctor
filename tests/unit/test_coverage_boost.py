"""Targeted tests to meet the core-module coverage gate (analyzers, connection)."""

from __future__ import annotations

import pytest

from redis_doctor.analyzers.config_rules import ConfigAnalyzer
from redis_doctor.analyzers.keyspace_rules import KeyspaceAnalyzer
from redis_doctor.collectors.keyspace import KeyspaceData, PrefixStat
from redis_doctor.config import Config
from redis_doctor.connection import parse_target
from redis_doctor.errors import ConnectionError as RDConnectionError
from redis_doctor.models.finding import Confidence, Severity
from redis_doctor.models.sample import KeyInfo, KeySample


@pytest.fixture
def ctx(safe_fake):
    from redis_doctor.pipeline import RunContext

    return RunContext(redis=safe_fake, config=Config())


def _ids(findings):
    return {f.id: f for f in findings}


# --- keyspace analyzer ----------------------------------------------------


def test_keyspace_dominant_prefix(ctx):
    keys = [KeyInfo(key=f"session:{i}", type="string", ttl_seconds=60) for i in range(80)]
    keys += [KeyInfo(key=f"other:{i}", type="string", ttl_seconds=60) for i in range(20)]
    ctx.collected["keyspace"] = KeyspaceData(
        sample=KeySample(scanned=100, estimated_total=100, confidence=Confidence.HIGH, keys=keys),
        dbsize=100,
        by_count=[PrefixStat("session", 80), PrefixStat("other", 20)],
    )
    f = _ids(KeyspaceAnalyzer().analyze(ctx))
    assert "keyspace.dominant_prefix" in f


def test_keyspace_high_key_count(ctx):
    keys = [KeyInfo(key=f"k:{i}", type="string", ttl_seconds=-1) for i in range(100)]
    ctx.collected["keyspace"] = KeyspaceData(
        sample=KeySample(
            scanned=100, estimated_total=2_000_000, confidence=Confidence.LOW, keys=keys
        ),
        dbsize=2_000_000,
        by_count=[PrefixStat("k", 100)],
    )
    f = _ids(KeyspaceAnalyzer().analyze(ctx))
    assert f["keyspace.high_key_count"].severity == Severity.WARNING


def test_keyspace_empty_sample(ctx):
    ctx.collected["keyspace"] = KeyspaceData(sample=KeySample(scanned=0))
    assert KeyspaceAnalyzer().analyze(ctx) == []


# --- config analyzer extra branches ---------------------------------------


def test_config_tcp_keepalive_and_slowlog_disabled(ctx):
    ctx.collected["config_values"] = {
        "maxmemory": "100",
        "maxmemory-policy": "allkeys-lru",
        "timeout": "60",
        "tcp-keepalive": "0",
        "appendonly": "no",
        "save": "3600 1",
        "slowlog-log-slower-than": "-1",
    }
    f = _ids(ConfigAnalyzer().analyze(ctx))
    assert "config.tcp_keepalive_bad" in f
    assert "config.slowlog_disabled" in f
    assert "config.risky_eviction_policy" not in f  # allkeys-lru is fine


def test_config_risky_eviction_policy(ctx):
    ctx.collected["config_values"] = {
        "maxmemory": "100",
        "maxmemory-policy": "noeviction",
        "timeout": "60",
        "tcp-keepalive": "300",
        "appendonly": "no",
        "save": "",
        "slowlog-log-slower-than": "10000",
    }
    f = _ids(ConfigAnalyzer().analyze(ctx))
    assert "config.risky_eviction_policy" in f
    # 'no persistence' is reported by the persistence module, not config.
    assert "config.no_persistence" not in f


# --- connection -----------------------------------------------------------


def test_safe_redis_pipe(safe_fake):
    safe_fake.client.set("a", "1")
    safe_fake.client.set("b", "hello")
    res = safe_fake.pipe([("TYPE", "a"), ("STRLEN", "b")])
    assert len(res) == 2
    # b is a 5-char string
    assert int(res[1]) == 5


def test_safe_redis_pipe_blocks_unsafe(safe_fake):
    from redis_doctor.errors import UnsafeCommandError

    with pytest.raises(UnsafeCommandError):
        safe_fake.pipe([("TYPE", "a"), ("KEYS", "*")])


def test_connect_bad_host_raises():
    from redis_doctor.connection import connect

    target = parse_target(
        host="nonexistent.invalid", port=6399, connect_timeout=1, socket_timeout=1
    )
    with pytest.raises(RDConnectionError):
        connect(target)


def test_parse_target_rediss_with_user_db():
    t = parse_target("rediss://alice:secret@host.example:7000/4")
    assert t.tls is True
    assert t.username == "alice"
    assert t.db == 4
    assert t.has_password is True
    assert "secret" not in t.redacted_url()


def test_safe_redis_close_is_safe(safe_fake):
    # close() must never raise.
    safe_fake.close()


def test_parse_target_unix_with_db():
    t = parse_target("unix:///tmp/redis.sock?db=2")
    assert t.socket_path == "/tmp/redis.sock"
    assert t.db == 2
    assert t.redacted_url().startswith("unix:///tmp/redis.sock")
