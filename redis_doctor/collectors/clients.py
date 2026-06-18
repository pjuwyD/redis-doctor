"""Client collector — CLIENT LIST parsing.

The parser is shared: the config analyzer uses it to count idle clients;
the full ClientCollector builds on it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.client import ClientInfo
from .base import Collector

if TYPE_CHECKING:
    from ..pipeline import RunContext


def parse_client_line(line: str) -> ClientInfo | None:
    line = line.strip()
    if not line:
        return None
    fields: dict[str, str] = {}
    for token in line.split():
        key, _, value = token.partition("=")
        fields[key] = value

    def _int(key: str) -> int:
        try:
            return int(fields.get(key, 0))
        except ValueError:
            return 0

    return ClientInfo(
        addr=fields.get("addr", ""),
        name=fields.get("name", ""),
        user=fields.get("user", ""),
        db=_int("db"),
        age_seconds=_int("age"),
        idle_seconds=_int("idle"),
        flags=fields.get("flags", ""),
        last_cmd=fields.get("cmd", ""),
        output_buffer=_int("omem"),
    )


def parse_client_list(text: str) -> list[ClientInfo]:
    clients: list[ClientInfo] = []
    for line in text.splitlines():
        info = parse_client_line(line)
        if info is not None:
            clients.append(info)
    return clients


def fetch_clients(redis) -> list[ClientInfo]:
    raw = redis.execute("CLIENT", "LIST")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    return parse_client_list(raw or "")


class ClientCollector(Collector):
    name = "clients"

    def collect(self, ctx: RunContext) -> list[ClientInfo]:
        return fetch_clients(ctx.redis)
