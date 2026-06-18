"""Finding-ID assertions for the streams, clients, and slowlog analyzers."""

from __future__ import annotations

import pytest

from redis_doctor.analyzers.client_rules import ClientAnalyzer
from redis_doctor.analyzers.slowlog_rules import SlowlogAnalyzer
from redis_doctor.analyzers.stream_rules import StreamAnalyzer
from redis_doctor.collectors.clients import parse_client_list
from redis_doctor.collectors.slowlog import redact_args
from redis_doctor.config import Config
from redis_doctor.models.client import ClientInfo
from redis_doctor.models.finding import Severity
from redis_doctor.models.server import ServerInfo
from redis_doctor.models.slowlog import SlowlogEntry
from redis_doctor.models.stream import StreamConsumer, StreamGroup, StreamInfo


@pytest.fixture
def ctx(safe_fake):
    from redis_doctor.pipeline import RunContext

    return RunContext(redis=safe_fake, config=Config())


def _ids(findings):
    return {f.id: f for f in findings}


def test_stream_pending_and_idle_consumer(ctx):
    ctx.config.thresholds.stream_pending_warning = 10
    ctx.config.thresholds.consumer_idle_warning_seconds = 1
    consumer = StreamConsumer(name="worker-7", pending=50, idle_ms=4_000_000)
    group = StreamGroup(name="g", consumers=1, pending=50, consumer_list=[consumer])
    ctx.collected["streams"] = [StreamInfo(name="s", length=100, groups=[group])]
    f = _ids(StreamAnalyzer().analyze(ctx))
    assert f["streams.pending_high"].severity == Severity.CRITICAL
    assert "streams.idle_consumer_with_pending" in f


def test_stream_no_consumers_and_no_groups(ctx):
    group = StreamGroup(name="g", consumers=0, pending=5)
    ctx.collected["streams"] = [
        StreamInfo(name="withgroup", length=10, groups=[group]),
        StreamInfo(name="bare", length=10, groups=[]),
    ]
    f = _ids(StreamAnalyzer().analyze(ctx))
    assert "streams.no_consumers" in f
    assert "streams.no_groups" in f


def test_stream_length_high(ctx):
    ctx.config.thresholds.stream_length_warning = 100
    ctx.collected["streams"] = [StreamInfo(name="s", length=500_000, groups=[])]
    f = _ids(StreamAnalyzer().analyze(ctx))
    assert f["streams.length_high"].severity == Severity.CRITICAL


def test_clients_idle_many_and_unnamed(ctx):
    ctx.config.thresholds.idle_client_warning_seconds = 10
    ctx.config.thresholds.idle_client_warning_count = 5
    ctx.config.thresholds.idle_client_critical_count = 100
    clients = [ClientInfo(addr=f"10.0.0.1:{i}", name="", idle_seconds=50) for i in range(30)]
    ctx.collected["clients"] = clients
    ctx.collected["info"] = ServerInfo(blocked_clients=0)
    f = _ids(ClientAnalyzer().analyze(ctx))
    assert f["clients.idle_many"].severity == Severity.WARNING
    assert "clients.unnamed" in f


def test_clients_blocked_critical(ctx):
    ctx.collected["clients"] = [ClientInfo(addr="10.0.0.1:1", name="svc")]
    ctx.collected["info"] = ServerInfo(blocked_clients=12)
    f = _ids(ClientAnalyzer().analyze(ctx))
    assert f["clients.blocked"].severity == Severity.CRITICAL


def test_clients_same_ip_many(ctx):
    clients = [ClientInfo(addr=f"10.0.0.9:{i}", name="svc") for i in range(60)]
    ctx.collected["clients"] = clients
    ctx.collected["info"] = ServerInfo()
    f = _ids(ClientAnalyzer().analyze(ctx))
    assert "clients.same_ip_many" in f


def test_slowlog_dangerous_and_repeated(ctx):
    entries = [SlowlogEntry(id=1, duration_us=5000, command="KEYS", args=["session:*"])]
    entries += [
        SlowlogEntry(id=i, duration_us=2000, command="HGETALL", args=["h"]) for i in range(6)
    ]
    ctx.collected["slowlog"] = {"length": 7, "entries": entries}
    f = _ids(SlowlogAnalyzer().analyze(ctx))
    assert f["slowlog.dangerous_command"].severity == Severity.CRITICAL
    assert "slowlog.repeated_slow_command" in f


def test_slowlog_length_near_max(ctx):
    entries = [SlowlogEntry(id=1, duration_us=1, command="GET", args=["k"])]
    ctx.collected["slowlog"] = {"length": 120, "entries": entries}
    ctx.collected["config_values"] = {"slowlog-max-len": "128"}
    f = _ids(SlowlogAnalyzer().analyze(ctx))
    assert "slowlog.length_near_max" in f


def test_slowlog_secret_redaction():
    assert redact_args("AUTH", ["supersecretpassword"]) == ["***"]
    long_token = "a" * 40
    assert redact_args("GET", [long_token]) == ["***"]
    assert redact_args("GET", ["user:1"]) == ["user:1"]


def test_parse_client_list():
    text = (
        "id=1 addr=127.0.0.1:5000 name=svc age=100 idle=50 flags=N db=0 cmd=get omem=0\n"
        "id=2 addr=127.0.0.1:5001 name= age=10 idle=5 flags=N db=0 cmd=ping omem=2048\n"
    )
    clients = parse_client_list(text)
    assert len(clients) == 2
    assert clients[0].name == "svc"
    assert clients[0].idle_seconds == 50
    assert clients[1].output_buffer == 2048
