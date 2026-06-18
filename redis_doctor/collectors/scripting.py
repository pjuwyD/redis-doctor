"""Scripting collector: Lua script cache stats + Redis Functions (7.0+).

Read-only. Legacy EVAL/EVALSHA scripts cannot be enumerated by Redis, so only the
cache count and memory are available (from INFO). The FUNCTION API (Redis 7.0+) is
fully introspectable; FUNCTION LIST is requested WITHOUT code (names/flags only).
Everything degrades gracefully on servers without FUNCTION support.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import Collector

if TYPE_CHECKING:
    from ..pipeline import RunContext


def _s(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value) if value is not None else ""


def _int(d: dict, key: str, default: int = 0) -> int:
    try:
        return int(d.get(key, default))
    except (ValueError, TypeError):
        return default


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


def _parse_function_stats(raw: Any) -> dict[str, Any]:
    """FUNCTION STATS -> {running_script, libraries_count, functions_count}."""
    out: dict[str, Any] = {"running_script": None, "libraries_count": 0, "functions_count": 0}
    if not isinstance(raw, dict):
        return out
    running = _get(raw, "running_script")
    if running:
        rd = {_s(k): running[k] for k in running} if isinstance(running, dict) else {}
        out["running_script"] = _s(_get(rd, "name", default="unknown"))
    engines = _get(raw, "engines")
    if isinstance(engines, dict):
        for eng in engines.values():
            ed = {_s(k): v for k, v in eng.items()} if isinstance(eng, dict) else {}
            out["libraries_count"] += _int(ed, "libraries_count")
            out["functions_count"] += _int(ed, "functions_count")
    return out


def _parse_function_list(raw: Any) -> list[dict[str, Any]]:
    libs: list[dict[str, Any]] = []
    for lib in raw or []:
        ld = {_s(k): v for k, v in lib.items()} if isinstance(lib, dict) else {}
        funcs = _get(ld, "functions") or []
        names = []
        for f in funcs:
            fd = {_s(k): v for k, v in f.items()} if isinstance(f, dict) else {}
            names.append(_s(_get(fd, "name")))
        libs.append({"name": _s(_get(ld, "library_name")), "functions": names})
    return libs


class ScriptingCollector(Collector):
    name = "scripting"

    def collect(self, ctx: RunContext) -> dict[str, Any]:
        f = ctx.info_fields()
        data: dict[str, Any] = {
            "cached_scripts": _int(f, "number_of_cached_scripts"),
            # used_memory_scripts on 7+, used_memory_lua on older servers.
            "scripts_memory": _int(f, "used_memory_scripts") or _int(f, "used_memory_lua"),
            "running_script": None,
            "libraries_count": 0,
            "functions_count": 0,
            "libraries": [],
            "functions_supported": False,
        }

        # FUNCTION STATS / LIST — unsupported before Redis 7.0; skip silently.
        try:
            stats = _parse_function_stats(ctx.redis.execute("FUNCTION", "STATS"))
            data.update(stats)
            data["functions_supported"] = True
        except Exception:
            return data
        try:
            data["libraries"] = _parse_function_list(ctx.redis.execute("FUNCTION", "LIST"))
        except Exception:
            pass
        return data
