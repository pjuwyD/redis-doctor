"""Stream collector (Section 9.7).

Finds stream-type keys in the keyspace sample (capped at 100) and reads
XLEN / XINFO STREAM / XINFO GROUPS / XINFO CONSUMERS for each.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..models.stream import StreamConsumer, StreamGroup, StreamInfo
from .base import Collector

if TYPE_CHECKING:
    from ..pipeline import RunContext

MAX_STREAMS = 100


def _get(d: Any, *names, default=None):
    """Fetch the first present key from a dict, tolerating bytes/str keys."""
    if not isinstance(d, dict):
        return default
    for name in names:
        if name in d:
            return d[name]
        b = name.encode()
        if b in d:
            return d[b]
    return default


def _s(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value) if value is not None else ""


def _i(value, default: int = 0) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def inspect_stream(redis, name: str) -> StreamInfo:
    info = StreamInfo(name=name)
    info.length = _i(redis.execute("XLEN", name))

    stream = redis.execute("XINFO", "STREAM", name)
    info.last_id = _s(_get(stream, "last-generated-id", default="0-0"))
    first_entry = _get(stream, "first-entry")
    if isinstance(first_entry, (list, tuple)) and first_entry:
        info.first_id = _s(first_entry[0])

    groups = redis.execute("XINFO", "GROUPS", name) or []
    for g in groups:
        group = StreamGroup(
            name=_s(_get(g, "name")),
            consumers=_i(_get(g, "consumers", default=0)),
            pending=_i(_get(g, "pending", default=0)),
            last_delivered_id=_s(_get(g, "last-delivered-id", default="0-0")),
            lag=_i(_get(g, "lag"), default=0) if _get(g, "lag") is not None else None,
        )
        try:
            consumers = redis.execute("XINFO", "CONSUMERS", name, group.name) or []
        except Exception:
            consumers = []
        for c in consumers:
            group.consumer_list.append(
                StreamConsumer(
                    name=_s(_get(c, "name")),
                    pending=_i(_get(c, "pending", default=0)),
                    idle_ms=_i(_get(c, "idle", default=0)),
                )
            )
        info.groups.append(group)
    return info


class StreamCollector(Collector):
    name = "streams"

    def collect(self, ctx: RunContext) -> list[StreamInfo]:
        keyspace = ctx.collected.get("keyspace")
        explicit = ctx.options.get("stream_names")
        if explicit:
            names = list(explicit)
        elif keyspace is not None:
            names = [k.key for k in keyspace.sample.keys if k.type == "stream"]
        else:
            return []

        streams: list[StreamInfo] = []
        for name in names[:MAX_STREAMS]:
            try:
                streams.append(inspect_stream(ctx.redis, name))
            except Exception as e:
                ctx.skip("streams", f"could not inspect stream {name}: {e}")
        return streams
