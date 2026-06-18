"""Security/hygiene collector (Section 9.14).

ACL output is aggressively redacted: password hashes (`#...`) and inline
passwords (`>...`) are masked. The requirepass value is never stored — only
whether one is set.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .base import Collector

if TYPE_CHECKING:
    from ..pipeline import RunContext

_ACL_SECRET = re.compile(r"(^|\s)([#>])(\S+)")


def redact_acl_line(line: str) -> str:
    """Mask password hashes (#...) and inline passwords (>...) in an ACL rule."""
    return _ACL_SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}***", line)


def _s(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value) if value is not None else ""


def _config_get(redis, key: str) -> str | None:
    try:
        res = redis.execute("CONFIG", "GET", key)
    except Exception:
        return None
    if isinstance(res, dict):
        return _s(next(iter(res.values()), ""))
    if isinstance(res, (list, tuple)) and len(res) >= 2:
        return _s(res[1])
    return None


class SecurityCollector(Collector):
    name = "security"

    def collect(self, ctx: RunContext) -> dict[str, Any]:
        data: dict[str, Any] = {}

        requirepass = _config_get(ctx.redis, "requirepass")
        data["requirepass_set"] = bool(requirepass)  # never store the value
        data["protected_mode"] = _config_get(ctx.redis, "protected-mode")

        try:
            data["whoami"] = _s(ctx.redis.execute("ACL", "WHOAMI"))
        except Exception:
            data["whoami"] = None

        try:
            raw = ctx.redis.execute("ACL", "LIST") or []
            data["acl_list"] = [redact_acl_line(_s(line)) for line in raw]
        except Exception:
            data["acl_list"] = None

        # Default-user usage from clients (reuse the clients collector if present).
        clients = ctx.collected.get("clients")
        if clients is None:
            try:
                from .clients import fetch_clients

                clients = fetch_clients(ctx.redis)
            except Exception:
                clients = []
        data["total_clients"] = len(clients)
        data["default_user_clients"] = sum(1 for c in clients if (c.user or "default") == "default")

        return data
