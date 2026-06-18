"""Finding-ID assertions for the TTL, big-key, and type analyzers, using a
synthetic keyspace sample."""

from __future__ import annotations

import pytest

from redis_doctor.analyzers.bigkey_rules import BigKeyAnalyzer
from redis_doctor.analyzers.ttl_rules import TTLAnalyzer
from redis_doctor.analyzers.type_rules import TypeAnalyzer
from redis_doctor.collectors.keyspace import KeyspaceData, group_prefixes
from redis_doctor.config import Config
from redis_doctor.models.finding import Severity
from redis_doctor.models.sample import KeyInfo, KeySample


def _keyspace(keys, dbsize=None):
    sample = KeySample(
        scanned=len(keys),
        estimated_total=dbsize if dbsize is not None else len(keys),
        complete=True,
        keys=keys,
    )
    by_count, by_memory = group_prefixes(keys, 2, ":.|/_")
    dist: dict[str, int] = {}
    for k in keys:
        dist[k.type] = dist.get(k.type, 0) + 1
    return KeyspaceData(
        sample=sample,
        dbsize=sample.estimated_total,
        by_count=by_count,
        by_memory=by_memory,
        type_distribution=dist,
    )


@pytest.fixture
def ctx(safe_fake):
    from redis_doctor.pipeline import RunContext

    return RunContext(redis=safe_fake, config=Config())


def _ids(findings):
    return {f.id: f for f in findings}


def test_locks_without_ttl_critical(ctx):
    keys = [KeyInfo(key=f"lock:{i}", type="string", ttl_seconds=-1) for i in range(20)]
    ctx.collected["keyspace"] = _keyspace(keys)
    f = _ids(TTLAnalyzer().analyze(ctx))
    assert f["ttl.locks_without_ttl"].severity == Severity.CRITICAL


def test_sessions_and_cache(ctx):
    keys = [KeyInfo(key=f"session:{i}", type="string", ttl_seconds=-1) for i in range(20)]
    keys += [KeyInfo(key=f"cache:{i}", type="string", ttl_seconds=-1) for i in range(20)]
    ctx.collected["keyspace"] = _keyspace(keys)
    f = _ids(TTLAnalyzer().analyze(ctx))
    assert "ttl.sessions_without_ttl" in f
    assert "ttl.cache_permanent" in f


def test_locks_with_ttl_not_flagged(ctx):
    keys = [KeyInfo(key=f"lock:{i}", type="string", ttl_seconds=60) for i in range(20)]
    ctx.collected["keyspace"] = _keyspace(keys)
    f = _ids(TTLAnalyzer().analyze(ctx))
    assert "ttl.locks_without_ttl" not in f


def test_inconsistent_within_prefix(ctx):
    keys = [KeyInfo(key=f"data:item:{i}", type="string", ttl_seconds=-1) for i in range(5)]
    keys += [KeyInfo(key=f"data:item:{i}", type="string", ttl_seconds=60) for i in range(5, 10)]
    ctx.collected["keyspace"] = _keyspace(keys)
    f = _ids(TTLAnalyzer().analyze(ctx))
    assert "ttl.inconsistent_within_prefix" in f


def test_excessive_ttl_from_expectations(ctx):
    from redis_doctor.config import TTLExpectation

    ctx.config.ttl_expectations = [TTLExpectation(pattern="lock:*", max_ttl_seconds=300)]
    keys = [KeyInfo(key="lock:1", type="string", ttl_seconds=99999)]
    ctx.collected["keyspace"] = _keyspace(keys)
    f = _ids(TTLAnalyzer().analyze(ctx))
    assert "ttl.excessive_ttl" in f


def test_bigkey_big_and_huge(ctx):
    keys = [
        KeyInfo(key="s:big", type="string", memory_bytes=80 * 1024 * 1024),
        KeyInfo(key="s:huge", type="string", memory_bytes=150 * 1024 * 1024),
    ]
    ctx.collected["keyspace"] = _keyspace(keys)
    f = _ids(BigKeyAnalyzer().analyze(ctx))
    assert f["bigkey.big_memory"].severity == Severity.WARNING
    assert f["bigkey.huge_memory"].severity == Severity.CRITICAL


def test_bigkey_collections(ctx):
    keys = [
        KeyInfo(key="l:large", type="list", memory_bytes=1000, element_count=20000),
        KeyInfo(key="z:huge", type="zset", memory_bytes=1000, element_count=200000),
    ]
    ctx.collected["keyspace"] = _keyspace(keys)
    f = _ids(BigKeyAnalyzer().analyze(ctx))
    assert f["bigkey.large_collection"].severity == Severity.WARNING
    assert f["bigkey.huge_collection"].severity == Severity.CRITICAL


def test_types_mixed_and_untrimmed(ctx):
    # All share depth-2 prefix "obj:user" but have two different value types.
    keys = [KeyInfo(key=f"obj:user:{i}", type="string", ttl_seconds=-1) for i in range(8)]
    keys += [KeyInfo(key=f"obj:user:{i}", type="hash", ttl_seconds=-1) for i in range(8, 10)]
    keys.append(KeyInfo(key="events:stream", type="stream", ttl_seconds=-1, element_count=5000))
    ctx.collected["keyspace"] = _keyspace(keys)
    f = _ids(TypeAnalyzer().analyze(ctx))
    assert "types.mixed_under_prefix" in f
    assert "types.untrimmed_collections" in f
