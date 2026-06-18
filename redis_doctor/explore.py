"""Explore service: browse keys and peek at their structure.

Two tiers, mirroring the safety model:

- **Metadata + bounded peek** (default, locked): key listing via SCAN, per-key
  type/TTL/memory/size, and a small bounded sample of contents using only
  cursor/range-bounded reads (HSCAN/SSCAN/ZSCAN/XRANGE COUNT, GETRANGE, LINDEX).
- **Full value read** (requires an unlocked `SafeRedis(allow_expensive=True)`):
  the whole value (GET/HGETALL/SMEMBERS/...), still capped to FULL_MAX_ELEMENTS /
  FULL_STRING_MAX_BYTES so even an unlock cannot pull an unbounded payload.

All value-returning reads tolerate non-UTF-8 data (shown as a placeholder).
"""

from __future__ import annotations

import re
from typing import Any

from .connection import SafeRedis
from .errors import UnsafeCommandError

PEEK_COUNT = 25  # elements in a bounded peek
FULL_MAX_ELEMENTS = 1000  # cap on a full collection read, even when unlocked
STRING_PREVIEW_BYTES = 4096  # bounded string slice
FULL_STRING_MAX_BYTES = 1_000_000  # refuse a full GET above this size

_SIZE_CMD = {
    "string": "STRLEN",
    "list": "LLEN",
    "set": "SCARD",
    "zset": "ZCARD",
    "hash": "HLEN",
    "stream": "XLEN",
}


def _s(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value if isinstance(value, str) else str(value)


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, Exception):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _get(d: Any, *names, default=None):
    if not isinstance(d, dict):
        return default
    for name in names:
        if name in d:
            return d[name]
        b = name.encode()
        if b in d:
            return d[b]
    return default


def function_overview(safe: SafeRedis, full: bool = False) -> dict[str, Any]:
    """Lua scripting + Functions overview for the Explore tab.

    Legacy EVAL/EVALSHA scripts cannot be enumerated by Redis, so only the cache
    count and memory are returned. Functions (Redis 7.0+) are listed by name;
    their source code is included only when `full` is set, which requires an
    unlocked connection (`allow_expensive`) — the same lock as full value reads.
    """
    if full and not safe.allow_expensive:
        raise UnsafeCommandError("reading function source requires unlocking full value reads")

    try:
        info = safe.execute("INFO", "memory")
        fields = info if isinstance(info, dict) else _parse_info_text(_s(info))
    except Exception:
        fields = {}
    out: dict[str, Any] = {
        "supported": False,
        "full": full,
        "cached_scripts": _intf(fields, "number_of_cached_scripts"),
        "scripts_memory": _intf(fields, "used_memory_scripts") or _intf(fields, "used_memory_lua"),
        "usage": _scripting_usage(safe),
        "libraries": [],
    }

    try:
        args = ("FUNCTION", "LIST", "WITHCODE") if full else ("FUNCTION", "LIST")
        raw = safe.execute(*args)
    except Exception:
        return out  # FUNCTION unsupported (Redis < 7) — return the script summary only
    out["supported"] = True

    for lib in raw or []:
        ld = {_s(k): v for k, v in lib.items()} if isinstance(lib, dict) else {}
        funcs = []
        for f in _get(ld, "functions") or []:
            fd = {_s(k): v for k, v in f.items()} if isinstance(f, dict) else {}
            flags = [_s(x) for x in (_get(fd, "flags") or [])]
            funcs.append({"name": _s(_get(fd, "name")), "flags": flags})
        code = _get(ld, "library_code")
        out["libraries"].append(
            {
                "name": _s(_get(ld, "library_name")),
                "engine": _s(_get(ld, "engine", default="")),
                "functions": funcs,
                "code": _s(code) if (full and code is not None) else None,
            }
        )
    return out


def _intf(d: dict, key: str) -> int:
    try:
        return int(d.get(key, 0))
    except (ValueError, TypeError):
        return 0


def _cmd_calls(cs: Any, key: str) -> int:
    """Calls for a `cmdstat_*` entry, from redis-py's nested dict or raw text."""
    v = _get(cs, key)
    if isinstance(v, dict):
        try:
            return int(v.get("calls", 0))
        except (ValueError, TypeError):
            return 0
    if isinstance(v, str):
        m = re.search(r"calls=(\d+)", v)
        return int(m.group(1)) if m else 0
    return 0


def _slowlog_tokens(entry: Any) -> list[str]:
    if isinstance(entry, dict):
        cmd = _get(entry, "command")
    elif isinstance(entry, (list, tuple)) and len(entry) >= 4:
        cmd = entry[3]
    else:
        return []
    if isinstance(cmd, (list, tuple)):
        return [_s(t) for t in cmd]
    return _s(cmd).split()


def _scripting_usage(safe: SafeRedis) -> dict[str, int]:
    """Scripting activity signals that work even with an empty cache / no FUNCTION.

    Call counts come from INFO commandstats (cumulative since start); the distinct
    count is a lower bound from whatever the slowlog happens to have captured.
    """
    usage = {
        "eval_calls": 0,
        "evalsha_calls": 0,
        "fcall_calls": 0,
        "slowlog_script_calls": 0,
        "distinct_in_slowlog": 0,
    }
    try:
        cs = safe.execute("INFO", "commandstats")
        cs = cs if isinstance(cs, dict) else _parse_info_text(_s(cs))
        usage["eval_calls"] = _cmd_calls(cs, "cmdstat_eval") + _cmd_calls(cs, "cmdstat_eval_ro")
        usage["evalsha_calls"] = _cmd_calls(cs, "cmdstat_evalsha") + _cmd_calls(
            cs, "cmdstat_evalsha_ro"
        )
        usage["fcall_calls"] = _cmd_calls(cs, "cmdstat_fcall") + _cmd_calls(cs, "cmdstat_fcall_ro")
    except Exception:
        pass
    try:
        distinct: set[str] = set()
        seen = 0
        for e in safe.execute("SLOWLOG", "GET", 128) or []:
            toks = _slowlog_tokens(e)
            if toks and toks[0].upper() in ("EVAL", "EVALSHA", "FCALL", "FCALL_RO"):
                seen += 1
                if len(toks) > 1:
                    distinct.add(f"{toks[0].upper()}:{toks[1]}")
        usage["slowlog_script_calls"] = seen
        usage["distinct_in_slowlog"] = len(distinct)
    except Exception:
        pass
    return usage


def _parse_info_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


def scan_page(
    safe: SafeRedis,
    match: str | None = None,
    cursor: int = 0,
    count: int = 500,
    page_limit: int = 200,
) -> dict[str, Any]:
    """One page of keys (with metadata) using SCAN. Never uses KEYS.

    Returns {cursor, keys:[{key,type,ttl,memory,size}], complete}.
    """
    names: list[str] = []
    iterations = 0
    cur = cursor
    while True:
        args: list[Any] = [cur]
        if match:
            args += ["MATCH", match]
        args += ["COUNT", count]
        cur, batch = safe.execute("SCAN", *args)
        cur = int(cur)
        for raw in batch:
            names.append(_s(raw))
        iterations += 1
        if cur == 0 or len(names) >= page_limit or iterations >= 50:
            break

    keys = _enrich(safe, names[:page_limit])
    return {"cursor": cur, "keys": keys, "complete": cur == 0}


def _enrich(safe: SafeRedis, names: list[str]) -> list[dict[str, Any]]:
    if not names:
        return []
    cmds: list[tuple] = []
    for k in names:
        cmds += [("TYPE", k), ("TTL", k), ("MEMORY", "USAGE", k)]
    res = safe.pipe(cmds)

    out: list[dict[str, Any]] = []
    size_cmds: list[tuple] = []
    size_targets: list[int] = []
    for i, k in enumerate(names):
        ktype = _s(res[3 * i]) if not isinstance(res[3 * i], Exception) else "none"
        item = {
            "key": k,
            "type": ktype,
            "ttl": _int_or_none(res[3 * i + 1]),
            "memory": _int_or_none(res[3 * i + 2]),
            "size": None,
        }
        out.append(item)
        size_cmd = _SIZE_CMD.get(ktype)
        if size_cmd:
            size_cmds.append((size_cmd, k))
            size_targets.append(len(out) - 1)
    if size_cmds:
        sizes = safe.pipe(size_cmds)
        for idx, value in zip(size_targets, sizes, strict=False):
            out[idx]["size"] = _int_or_none(value)
    return out


def key_detail(safe: SafeRedis, key: str, full: bool = False) -> dict[str, Any]:
    """Metadata + a peek at a single key.

    `full=True` reads the whole value and requires the connection to be unlocked
    (`allow_expensive=True`); otherwise only a bounded peek is returned.
    """
    if full and not safe.allow_expensive:
        raise UnsafeCommandError("full value read requires unlocking full value reads")

    ktype = _s(safe.execute("TYPE", key))
    if ktype == "none":
        return {"key": key, "exists": False}

    size_cmd = _SIZE_CMD.get(ktype)
    detail: dict[str, Any] = {
        "key": key,
        "exists": True,
        "type": ktype,
        # Optional metadata: degrade to None if a command is denied/unsupported.
        "ttl": _int_or_none(_safe(lambda: safe.execute("TTL", key))),
        "memory": _int_or_none(_safe(lambda: safe.execute("MEMORY", "USAGE", key))),
        "encoding": _safe(lambda: _s(safe.execute("OBJECT", "ENCODING", key))),
        "size": _int_or_none(_safe(lambda: safe.execute(size_cmd, key))) if size_cmd else None,
    }

    detail["preview_mode"] = "full" if full else "bounded"
    detail["preview"], detail["truncated"] = _preview(safe, key, ktype, detail["size"], full)
    return detail


def _preview(
    safe: SafeRedis, key: str, ktype: str, size: int | None, full: bool
) -> tuple[Any, bool]:
    try:
        if ktype == "string":
            return _string_preview(safe, key, size, full)
        if ktype == "hash":
            return _hash_preview(safe, key, full)
        if ktype == "set":
            return _set_preview(safe, key, full)
        if ktype == "zset":
            return _zset_preview(safe, key, full)
        if ktype == "list":
            return _list_preview(safe, key, size, full)
        if ktype == "stream":
            return _stream_preview(safe, key, full)
    except Exception as e:  # never let a peek crash the request
        return {"error": str(e)}, False
    return None, False


def _string_preview(safe, key, size, full) -> tuple[Any, bool]:
    if full:
        if size is not None and size > FULL_STRING_MAX_BYTES:
            return {"note": f"value is {size} bytes; too large to fetch in full"}, True
        return _s(safe.execute("GET", key)), False
    sliced = _s(safe.execute("GETRANGE", key, 0, STRING_PREVIEW_BYTES - 1))
    truncated = size is not None and size > STRING_PREVIEW_BYTES
    return sliced, truncated


def _hash_preview(safe, key, full) -> tuple[Any, bool]:
    if full:
        items = _dict_capped(safe.execute("HGETALL", key))
        return items, len(items) >= FULL_MAX_ELEMENTS
    _cur, batch = safe.execute("HSCAN", key, 0, "COUNT", PEEK_COUNT)
    pairs = _scan_pairs(batch)[:PEEK_COUNT]
    return {k: v for k, v in pairs}, True


def _set_preview(safe, key, full) -> tuple[Any, bool]:
    if full:
        members = _scan_members(safe.execute("SMEMBERS", key))
        return members[:FULL_MAX_ELEMENTS], len(members) > FULL_MAX_ELEMENTS
    _cur, batch = safe.execute("SSCAN", key, 0, "COUNT", PEEK_COUNT)
    return _scan_members(batch)[:PEEK_COUNT], True


def _zset_preview(safe, key, full) -> tuple[Any, bool]:
    if full:
        raw = safe.execute("ZRANGE", key, 0, FULL_MAX_ELEMENTS - 1, "WITHSCORES")
        return _scan_pairs(raw), False
    _cur, batch = safe.execute("ZSCAN", key, 0, "COUNT", PEEK_COUNT)
    return _scan_pairs(batch)[:PEEK_COUNT], True


def _list_preview(safe, key, size, full) -> tuple[Any, bool]:
    if full:
        items = [_s(x) for x in (safe.execute("LRANGE", key, 0, FULL_MAX_ELEMENTS - 1) or [])]
        return items, size is not None and size > FULL_MAX_ELEMENTS
    head = _s(safe.execute("LINDEX", key, 0))
    tail = _s(safe.execute("LINDEX", key, -1))
    return {"head": head, "tail": tail}, (size or 0) > 2


def _stream_preview(safe, key, full) -> tuple[Any, bool]:
    n = FULL_MAX_ELEMENTS if full else PEEK_COUNT
    entries = safe.execute("XRANGE", key, "-", "+", "COUNT", n) or []
    out = [{"id": _s(e[0]), "fields": _dict_capped(e[1])} for e in entries]
    return out, not full


def _scan_pairs(batch) -> list[tuple[str, str]]:
    """Normalize a hash/zset reply (dict, list-of-tuples, or flat list) to pairs."""
    if isinstance(batch, dict):
        return [(_s(k), _s(v)) for k, v in batch.items()]
    if batch and isinstance(batch[0], (list, tuple)):
        return [(_s(p[0]), _s(p[1])) for p in batch]
    return [(_s(batch[i]), _s(batch[i + 1])) for i in range(0, len(batch) - 1, 2)]


def _scan_members(batch) -> list[str]:
    return [_s(x) for x in (batch or [])]


def _dict_capped(raw) -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(raw, dict):
        for k, v in list(raw.items())[:FULL_MAX_ELEMENTS]:
            out[_s(k)] = _s(v)
    elif isinstance(raw, (list, tuple)):
        for i in range(0, min(len(raw) - 1, FULL_MAX_ELEMENTS * 2), 2):
            out[_s(raw[i])] = _s(raw[i + 1])
    return out


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None
