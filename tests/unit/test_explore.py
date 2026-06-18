"""Explore service + the expensive-read (full value) lock."""

from __future__ import annotations

import pytest

from redis_doctor import explore, safety
from redis_doctor.connection import SafeRedis
from redis_doctor.errors import UnsafeCommandError
from redis_doctor.models.target import RedisTarget

# --- safety tiers ---------------------------------------------------------


def test_bounded_reads_allowed_by_default():
    for cmd, args in [
        ("HSCAN", ("k", 0)),
        ("SSCAN", ("k", 0)),
        ("ZSCAN", ("k", 0)),
        ("XRANGE", ("k", "-", "+")),
        ("GETRANGE", ("k", 0, 10)),
        ("LINDEX", ("k", 0)),
        ("OBJECT", ("ENCODING", "k")),
    ]:
        safety.check_command(cmd, *args)  # must not raise


def test_full_reads_locked_by_default():
    for cmd, args in [
        ("GET", ("k",)),
        ("HGETALL", ("k",)),
        ("SMEMBERS", ("k",)),
        ("LRANGE", ("k", 0, -1)),
        ("ZRANGE", ("k", 0, -1)),
    ]:
        with pytest.raises(UnsafeCommandError):
            safety.check_command(cmd, *args)
        safety.check_command(cmd, *args, allow_expensive=True)  # unlocked -> ok


def test_full_reads_are_not_writes():
    # allow_write must NOT unlock expensive reads; only allow_expensive does.
    with pytest.raises(UnsafeCommandError):
        safety.check_command("GET", "k", allow_write=True)


def test_getdel_is_a_write_not_expensive_read():
    with pytest.raises(UnsafeCommandError):
        safety.check_command("GETDEL", "k", allow_expensive=True)
    safety.check_command("GETDEL", "k", allow_write=True)


# --- explore service (fakeredis) ------------------------------------------


@pytest.fixture
def locked(fake_redis):
    return SafeRedis(fake_redis, RedisTarget(host="fake"), allow_expensive=False)


@pytest.fixture
def unlocked(fake_redis):
    return SafeRedis(fake_redis, RedisTarget(host="fake"), allow_expensive=True)


def _seed(client):
    client.set("s:str", "x" * 500)
    client.hset("s:hash", mapping={f"f{i}": f"v{i}" for i in range(50)})
    client.rpush("s:list", *[f"item{i}" for i in range(40)])
    client.sadd("s:set", *[f"m{i}" for i in range(30)])
    client.zadd("s:zset", {f"z{i}": i for i in range(30)})


def test_scan_page_lists_keys_with_metadata(locked):
    _seed(locked.client)
    page = explore.scan_page(locked, match="s:*", count=100)
    by_key = {k["key"]: k for k in page["keys"]}
    assert by_key["s:hash"]["type"] == "hash"
    assert by_key["s:hash"]["size"] == 50
    assert by_key["s:list"]["size"] == 40
    assert page["complete"] is True


def test_bounded_peek_is_capped(locked):
    _seed(locked.client)
    d = explore.key_detail(locked, "s:hash", full=False)
    assert d["preview_mode"] == "bounded"
    assert len(d["preview"]) <= explore.PEEK_COUNT
    assert d["truncated"] is True


def test_bounded_string_slice(locked):
    locked.client.set("s:str", "y" * (explore.STRING_PREVIEW_BYTES + 100))
    d = explore.key_detail(locked, "s:str", full=False)
    assert len(d["preview"]) == explore.STRING_PREVIEW_BYTES
    assert d["truncated"] is True


def test_full_peek_requires_unlock(locked):
    _seed(locked.client)
    with pytest.raises(UnsafeCommandError):
        explore.key_detail(locked, "s:hash", full=True)


def test_full_peek_when_unlocked(unlocked):
    _seed(unlocked.client)
    d = explore.key_detail(unlocked, "s:hash", full=True)
    assert d["preview_mode"] == "full"
    assert len(d["preview"]) == 50  # whole hash


def test_list_bounded_head_tail(locked):
    _seed(locked.client)
    d = explore.key_detail(locked, "s:list", full=False)
    assert d["preview"]["head"] == "item0"
    assert d["preview"]["tail"] == "item39"


def test_missing_key(locked):
    d = explore.key_detail(locked, "nope", full=False)
    assert d["exists"] is False


def test_function_overview_returns_script_summary(locked):
    # fakeredis has no FUNCTION support, so this exercises the degrade path:
    # script cache summary is returned and supported is False.
    out = explore.function_overview(locked, full=False)
    assert out["supported"] is False
    assert "cached_scripts" in out and "scripts_memory" in out
    assert out["libraries"] == []


def test_function_overview_full_requires_unlock(locked):
    with pytest.raises(UnsafeCommandError):
        explore.function_overview(locked, full=True)


def test_function_overview_full_allowed_when_unlocked(unlocked):
    out = explore.function_overview(unlocked, full=True)  # must not raise
    assert out["full"] is True
    assert "usage" in out  # call-count usage signals are always present


def test_cmd_calls_parses_dict_and_text():
    assert explore._cmd_calls({"cmdstat_eval": {"calls": 12}}, "cmdstat_eval") == 12
    assert explore._cmd_calls({"cmdstat_eval": "calls=9,usec=3"}, "cmdstat_eval") == 9
    assert explore._cmd_calls({}, "cmdstat_eval") == 0


def test_slowlog_tokens_from_dict_and_list():
    assert explore._slowlog_tokens({"command": "EVALSHA abc 0"}) == ["EVALSHA", "abc", "0"]
    assert explore._slowlog_tokens({"command": ["EVAL", "return 1", "0"]}) == [
        "EVAL",
        "return 1",
        "0",
    ]
    assert explore._slowlog_tokens([1, 2, 3, "EVAL body 0"]) == ["EVAL", "body", "0"]
