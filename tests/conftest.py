"""Shared fixtures: fakeredis for unit tests, a real Redis for integration.

The real-Redis fixture connects to REDIS_DOCTOR_TEST_URL (default redis://redis:6379)
and skips integration tests gracefully when no server is reachable.
"""

from __future__ import annotations

import os

import pytest

REAL_REDIS_URL = os.environ.get("REDIS_DOCTOR_TEST_URL", "redis://redis:6379")


@pytest.fixture
def fake_redis():
    import fakeredis

    server = fakeredis.FakeServer()
    return fakeredis.FakeStrictRedis(server=server, decode_responses=True)


@pytest.fixture
def safe_fake(fake_redis):
    from redis_doctor.connection import SafeRedis
    from redis_doctor.models.target import RedisTarget

    return SafeRedis(fake_redis, RedisTarget(host="fake"))


@pytest.fixture(scope="session")
def real_redis_url() -> str:
    import redis

    try:
        client = redis.Redis.from_url(REAL_REDIS_URL, socket_connect_timeout=2)
        client.ping()
        client.close()
    except Exception:
        pytest.skip(f"no real Redis reachable at {REAL_REDIS_URL}")
    return REAL_REDIS_URL
