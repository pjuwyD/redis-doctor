import pytest

from redis_doctor import safety
from redis_doctor.errors import UnsafeCommandError


def test_keys_blocked_unconditionally():
    with pytest.raises(UnsafeCommandError):
        safety.check_command("KEYS", "*")
    with pytest.raises(UnsafeCommandError):
        safety.check_command("KEYS", "*", allow_write=True)
    assert safety.is_blocked_unconditionally("keys")


def test_monitor_blocked_unconditionally():
    with pytest.raises(UnsafeCommandError):
        safety.check_command("MONITOR", allow_write=True)


def test_read_commands_allowed():
    for cmd, args in [
        ("PING", ()),
        ("INFO", ("memory",)),
        ("CONFIG", ("GET", "maxmemory")),
        ("SCAN", ("0",)),
        ("MEMORY", ("USAGE", "k")),
        ("XINFO", ("STREAM", "s")),
        ("CLIENT", ("LIST",)),
        ("SLOWLOG", ("GET", "128")),
    ]:
        safety.check_command(cmd, *args)  # must not raise


def test_config_set_requires_allow_write():
    with pytest.raises(UnsafeCommandError):
        safety.check_command("CONFIG", "SET", "maxmemory", "0")
    safety.check_command("CONFIG", "SET", "maxmemory", "0", allow_write=True)


def test_write_commands_blocked():
    for cmd, args in [("FLUSHALL", ()), ("DEL", ("k",)), ("CLIENT", ("KILL", "x"))]:
        with pytest.raises(UnsafeCommandError):
            safety.check_command(cmd, *args)


def test_unknown_command_default_denied():
    with pytest.raises(UnsafeCommandError):
        safety.check_command("FROBNICATE")


def test_safe_redis_blocks_keys(safe_fake):
    with pytest.raises(UnsafeCommandError):
        safe_fake.execute("KEYS", "*")
