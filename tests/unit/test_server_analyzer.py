from redis_doctor.collectors.info import build_server_info, parse_info
from redis_doctor.config import Config
from redis_doctor.pipeline import run_pipeline


def test_parse_info_basic():
    raw = (
        "# Server\r\nredis_version:6.2.1\r\nuptime_in_seconds:100\r\n"
        "# Keyspace\r\ndb0:keys=5,expires=2,avg_ttl=0\r\n"
    )
    fields = parse_info(raw)
    info = build_server_info(fields)
    assert info.redis_version == "6.2.1"
    assert info.uptime_seconds == 100
    assert info.total_keys == 5


def test_server_findings(safe_fake):
    report = run_pipeline(safe_fake, Config())
    ids = {f.id for f in report.findings}
    # fakeredis reports an old version and uptime 0; nothing should crash.
    assert report.health_score <= 100
    assert isinstance(ids, set)


def test_version_outdated_and_evictions(safe_fake):
    # Seed a fake INFO via monkeypatched execute would be heavy; instead test the
    # analyzer logic through build_server_info + ServerAnalyzer directly.
    from redis_doctor.analyzers.server_rules import ServerAnalyzer
    from redis_doctor.models.server import ServerInfo
    from redis_doctor.pipeline import RunContext

    ctx = RunContext(redis=safe_fake, config=Config())
    ctx.collected["info"] = ServerInfo(
        redis_version="5.0.7", evicted_keys=10, blocked_clients=3, uptime_seconds=500
    )
    findings = ServerAnalyzer().analyze(ctx)
    ids = {f.id for f in findings}
    assert "server.version_outdated" in ids
    assert "server.evictions_occurring" in ids
    assert "server.blocked_clients" in ids
    assert "server.recent_restart" in ids
