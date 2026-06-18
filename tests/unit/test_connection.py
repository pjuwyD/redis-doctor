import pytest

from redis_doctor import logging as rdlogging
from redis_doctor.connection import parse_target
from redis_doctor.errors import ConnectionError as RDConnectionError


def test_parse_url_basic():
    t = parse_target("redis://host.example:6380/3")
    assert t.host == "host.example"
    assert t.port == 6380
    assert t.db == 3
    assert t.tls is False
    assert t.has_password is False


def test_parse_url_with_password_redacted():
    t = parse_target("redis://user:secret@host:6379/0")
    assert t.username == "user"
    assert t.has_password is True
    assert "secret" not in t.redacted_url()
    assert "***" in t.redacted_url()
    # password must not serialize
    assert "secret" not in t.model_dump_json()


def test_parse_rediss_tls():
    t = parse_target("rediss://host:6379")
    assert t.tls is True


def test_parse_unix_socket():
    t = parse_target("unix:///var/run/redis/redis.sock")
    assert t.socket_path == "/var/run/redis/redis.sock"


def test_flags_override_url():
    t = parse_target("redis://host:6379/0", port=7000, db=5)
    assert t.port == 7000
    assert t.db == 5


def test_bad_scheme():
    with pytest.raises(RDConnectionError):
        parse_target("http://host:6379")


def test_secret_scrubbing(monkeypatch):
    rdlogging.clear_secrets()
    rdlogging.register_secret("hunter2")
    assert rdlogging.scrub("password is hunter2 here") == "password is *** here"
    assert "topsecret" not in rdlogging.scrub("redis://u:topsecret@h:6379")
