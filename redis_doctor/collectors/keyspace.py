"""Keyspace sampling engine (Section 6) + prefix grouping.

Uses SCAN with COUNT, never KEYS. Stops when the sample size or max scan time is
reached. Enriches each sampled key with type, TTL, memory, and element count so
the TTL, big-key, and type analyzers can reuse one sample.
"""

from __future__ import annotations

import fnmatch
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..models.finding import Confidence
from ..models.sample import KeyInfo, KeySample
from .base import Collector

if TYPE_CHECKING:
    from ..pipeline import RunContext

# Size command per Redis type.
_SIZE_CMD = {
    "string": "STRLEN",
    "list": "LLEN",
    "set": "SCARD",
    "zset": "ZCARD",
    "hash": "HLEN",
    "stream": "XLEN",
}


def tokenize_prefix(key: str, depth: int, separators: str) -> str:
    """Return the first `depth` tokens of a key joined by the first separator seen.

    `session:user:123` depth 2 -> `session:user`.
    """
    if not separators:
        return key
    # Build a split pattern of the separator characters.
    tokens: list[str] = []
    current = []
    seps_used: list[str] = []
    for ch in key:
        if ch in separators:
            tokens.append("".join(current))
            seps_used.append(ch)
            current = []
            if len(tokens) >= depth:
                break
        else:
            current.append(ch)
    if len(tokens) < depth:
        tokens.append("".join(current))
        return key if len(tokens) == 1 else _join(tokens, seps_used)
    return _join(tokens[:depth], seps_used[:depth])


def _join(tokens: list[str], seps: list[str]) -> str:
    out = tokens[0]
    for i, tok in enumerate(tokens[1:]):
        sep = seps[i] if i < len(seps) else ":"
        out += sep + tok
    return out


@dataclass
class PrefixStat:
    prefix: str
    count: int = 0
    memory_bytes: int = 0


@dataclass
class KeyspaceData:
    sample: KeySample
    dbsize: int = 0
    by_count: list[PrefixStat] = field(default_factory=list)
    by_memory: list[PrefixStat] = field(default_factory=list)
    type_distribution: dict[str, int] = field(default_factory=dict)


def group_prefixes(
    keys: list[KeyInfo], depth: int, separators: str
) -> tuple[list[PrefixStat], list[PrefixStat]]:
    stats: dict[str, PrefixStat] = {}
    for ki in keys:
        prefix = tokenize_prefix(ki.key, depth, separators)
        st = stats.setdefault(prefix, PrefixStat(prefix=prefix))
        st.count += 1
        st.memory_bytes += ki.memory_bytes or 0
    by_count = sorted(stats.values(), key=lambda s: s.count, reverse=True)
    by_memory = sorted(stats.values(), key=lambda s: s.memory_bytes, reverse=True)
    return by_count, by_memory


def _confidence(scanned: int, dbsize: int) -> Confidence:
    if dbsize <= 0:
        return Confidence.HIGH
    ratio = scanned / dbsize
    if ratio >= 0.5 or dbsize <= scanned:
        return Confidence.HIGH
    if ratio >= 0.05:
        return Confidence.MEDIUM
    return Confidence.LOW


class KeyspaceCollector(Collector):
    name = "keyspace"

    def collect(self, ctx: RunContext) -> KeyspaceData:
        scan = ctx.config.scan
        ignore_patterns = ctx.config.ignore.keys
        start = time.monotonic()

        try:
            dbsize = int(ctx.redis.execute("DBSIZE"))
        except Exception:
            dbsize = 0

        key_names = self._scan_keys(ctx, scan, ignore_patterns, start)
        scan_finished = self._scan_finished
        elapsed = time.monotonic() - start

        keys, vanished = self._enrich(ctx, key_names)
        if vanished:
            ctx.skip(
                "keyspace",
                f"MEMORY USAGE skipped for {vanished} keys: keys expired during scan",
            )

        scanned = len(key_names)
        complete = scan_finished and scanned >= dbsize
        if not complete:
            ctx.sampled = True

        sample = KeySample(
            scanned=scanned,
            estimated_total=dbsize,
            duration_seconds=round(elapsed, 3),
            complete=complete,
            confidence=_confidence(scanned, dbsize),
            keys=keys,
        )

        by_count, by_memory = group_prefixes(keys, scan.prefix_depth, scan.prefix_separators)
        type_dist: dict[str, int] = {}
        for ki in keys:
            type_dist[ki.type] = type_dist.get(ki.type, 0) + 1

        return KeyspaceData(
            sample=sample,
            dbsize=dbsize,
            by_count=by_count,
            by_memory=by_memory,
            type_distribution=type_dist,
        )

    def _scan_keys(self, ctx, scan, ignore_patterns, start) -> list[str]:
        names: list[str] = []
        cursor = 0
        self._scan_finished = False
        while True:
            cursor, batch = ctx.redis.execute("SCAN", cursor, "COUNT", scan.count)
            cursor = int(cursor)
            for raw in batch:
                key = raw.decode() if isinstance(raw, bytes) else str(raw)
                if any(fnmatch.fnmatch(key, p) for p in ignore_patterns):
                    continue
                names.append(key)
            if cursor == 0:
                self._scan_finished = True
                break
            if len(names) >= scan.sample_size:
                break
            if (time.monotonic() - start) >= scan.max_seconds:
                break
        return names[: scan.sample_size]

    def _enrich(self, ctx, key_names: list[str]) -> tuple[list[KeyInfo], int]:
        if not key_names:
            return [], 0

        # Pass 1: TYPE, TTL, MEMORY USAGE per key.
        cmds: list[tuple] = []
        for k in key_names:
            cmds.append(("TYPE", k))
            cmds.append(("TTL", k))
            cmds.append(("MEMORY", "USAGE", k))
        res = ctx.redis.pipe(cmds)

        infos: list[KeyInfo] = []
        size_cmds: list[tuple] = []
        size_targets: list[int] = []
        vanished = 0
        for i, k in enumerate(key_names):
            ktype = _as_str(res[3 * i])
            ttl = _as_int(res[3 * i + 1], -1)
            mem = _as_int_or_none(res[3 * i + 2])
            if ktype in ("none", ""):
                vanished += 1
                infos.append(KeyInfo(key=k, type="none", ttl_seconds=-2, memory_bytes=mem))
                continue
            info = KeyInfo(key=k, type=ktype, ttl_seconds=ttl, memory_bytes=mem)
            infos.append(info)
            size_cmd = _SIZE_CMD.get(ktype)
            if size_cmd:
                size_cmds.append((size_cmd, k))
                size_targets.append(len(infos) - 1)

        # Pass 2: element counts for collection types.
        if size_cmds:
            size_res = ctx.redis.pipe(size_cmds)
            for idx, value in zip(size_targets, size_res, strict=False):
                infos[idx].element_count = _as_int_or_none(value)

        return infos, vanished


def _as_str(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, Exception):
        return "none"
    return str(value) if value is not None else "none"


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _as_int_or_none(value):
    if value is None or isinstance(value, Exception):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
