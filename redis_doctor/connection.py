"""Connection handling: parse targets, connect, redact, enforce safety.

`SafeRedis` wraps a redis-py client and routes every command through
`safety.check_command` before execution, so no analyzer can issue an unsafe
command even by accident.
"""

from __future__ import annotations

import ssl
from urllib.parse import parse_qs, unquote, urlparse

import redis

from . import safety
from .errors import ConnectionError as RDConnectionError
from .logging import register_secret
from .models.target import RedisTarget


def parse_target(
    url: str | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
    db: int | None = None,
    username: str | None = None,
    password: str | None = None,
    tls: bool = False,
    tls_ca_cert: str | None = None,
    tls_cert: str | None = None,
    tls_key: str | None = None,
    socket_timeout: float = 5.0,
    connect_timeout: float = 5.0,
) -> RedisTarget:
    """Build a RedisTarget from a URL and/or explicit flags. Flags override URL."""
    t = RedisTarget(
        socket_timeout=socket_timeout,
        connect_timeout=connect_timeout,
        tls=tls,
        tls_ca_cert=tls_ca_cert,
        tls_cert=tls_cert,
        tls_key=tls_key,
    )

    if url:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme == "unix":
            t.socket_path = parsed.path or None
            qs = parse_qs(parsed.query)
            if "db" in qs:
                t.db = int(qs["db"][0])
        elif scheme in ("redis", "rediss"):
            t.tls = scheme == "rediss"
            if parsed.hostname:
                t.host = parsed.hostname
            if parsed.port:
                t.port = parsed.port
            if parsed.username:
                t.username = unquote(parsed.username)
            if parsed.password is not None:
                t.password = unquote(parsed.password)
            path = parsed.path.lstrip("/")
            if path:
                t.db = int(path)
        else:
            raise RDConnectionError(f"Unsupported scheme: {parsed.scheme!r}")

    # Explicit flags take precedence.
    if host is not None:
        t.host = host
    if port is not None:
        t.port = port
    if db is not None:
        t.db = db
    if username is not None:
        t.username = username
    if password is not None:
        t.password = password

    t.has_password = bool(t.password)
    register_secret(t.password)
    return t


class SafeRedis:
    """A redis-py client that refuses unsafe commands.

    Use `.execute(command, *args)` for guarded execution, or the convenience
    wrappers. `allow_write` defaults to False everywhere. `allow_expensive`
    unlocks full-value reads (the Explore tab's "unlock") and defaults to False.
    """

    def __init__(
        self,
        client: redis.Redis,
        target: RedisTarget,
        allow_write: bool = False,
        allow_expensive: bool = False,
    ):
        self.client = client
        self.target = target
        self.allow_write = allow_write
        self.allow_expensive = allow_expensive

    def execute(self, command: str, *args: object):
        safety.check_command(
            command, *args, allow_write=self.allow_write, allow_expensive=self.allow_expensive
        )
        return self.client.execute_command(command, *args)

    def pipe(self, commands: list[tuple]) -> list:
        """Run many read commands in one pipeline. Each item is (cmd, *args).

        Every command is safety-checked first. Per-command errors are returned
        as exception objects in the result list (the pipeline does not abort).
        """
        for cmd, *args in commands:
            safety.check_command(
                cmd, *args, allow_write=self.allow_write, allow_expensive=self.allow_expensive
            )
        pipe = self.client.pipeline(transaction=False)
        for cmd, *args in commands:
            pipe.execute_command(cmd, *args)
        return pipe.execute(raise_on_error=False)

    def ping(self) -> bool:
        return bool(self.execute("PING"))

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass


def _build_kwargs(target: RedisTarget) -> dict:
    kwargs: dict = {
        "db": target.db,
        "username": target.username,
        "password": target.password,
        "socket_timeout": target.socket_timeout,
        "socket_connect_timeout": target.connect_timeout,
        "decode_responses": True,
    }
    if target.socket_path:
        kwargs["unix_socket_path"] = target.socket_path
    else:
        kwargs["host"] = target.host
        kwargs["port"] = target.port
    if target.tls:
        kwargs["ssl"] = True
        kwargs["ssl_ca_certs"] = target.tls_ca_cert
        kwargs["ssl_certfile"] = target.tls_cert
        kwargs["ssl_keyfile"] = target.tls_key
        kwargs["ssl_cert_reqs"] = ssl.CERT_REQUIRED if target.tls_ca_cert else ssl.CERT_NONE
    return kwargs


def connect(
    target: RedisTarget, allow_write: bool = False, allow_expensive: bool = False
) -> SafeRedis:
    """Open a connection and verify it with PING. Raises RDConnectionError on failure."""
    try:
        client = redis.Redis(**_build_kwargs(target))
        safe = SafeRedis(client, target, allow_write=allow_write, allow_expensive=allow_expensive)
        safe.ping()
        return safe
    except redis.AuthenticationError as e:
        raise RDConnectionError(f"Authentication failed: {e}") from e
    except (redis.ConnectionError, redis.TimeoutError, OSError) as e:
        raise RDConnectionError(f"Could not connect to {target.redacted_url()}: {e}") from e
