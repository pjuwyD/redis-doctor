from redis_doctor.collectors.keyspace import KeyspaceCollector
from redis_doctor.config import Config
from redis_doctor.pipeline import RunContext


def _ctx(safe_fake):
    return RunContext(redis=safe_fake, config=Config())


def test_keyspace_collector_samples_and_groups(safe_fake):
    for i in range(30):
        safe_fake.client.set(f"session:user:{i}", "x" * 20)
    for i in range(10):
        safe_fake.client.set(f"cache:item:{i}", "y" * 10)

    ctx = _ctx(safe_fake)
    data = KeyspaceCollector().collect(ctx)

    assert data.dbsize == 40
    assert data.sample.scanned == 40
    assert data.sample.complete is True
    assert data.by_count[0].prefix == "session:user"
    assert data.by_count[0].count == 30
    assert "string" in data.type_distribution
    assert data.type_distribution["string"] == 40


def test_keyspace_ignore_patterns(safe_fake):
    for i in range(5):
        safe_fake.client.set(f"keep:{i}", "1")
    for i in range(5):
        safe_fake.client.set(f"metrics:{i}", "1")

    ctx = _ctx(safe_fake)
    ctx.config.ignore.keys = ["metrics:*"]
    data = KeyspaceCollector().collect(ctx)

    prefixes = {p.prefix for p in data.by_count}
    assert not any(p.startswith("metrics") for p in prefixes)
    assert data.sample.scanned == 5


def test_keyspace_records_ttl(safe_fake):
    safe_fake.client.set("a", "1")
    safe_fake.client.set("b", "1", ex=100)
    ctx = _ctx(safe_fake)
    data = KeyspaceCollector().collect(ctx)
    ttls = {k.key: k.ttl_seconds for k in data.sample.keys}
    assert ttls["a"] == -1
    assert 0 < ttls["b"] <= 100
