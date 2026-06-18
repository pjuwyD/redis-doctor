"""Finding suppression / acknowledgement.

A suppression mutes a specific finding for a time window without permanently
disabling its rule (which is what `ignore.rules` does). It is matched by finding
id, optionally scoped to a particular affected item and/or target, and expires at
`until`. Suppressed findings are removed from the scored findings (so they do not
affect the health score or exit code) but reported separately for transparency.

Persisted in a small SQLite store, default ~/.redis-doctor/suppressions.db, so it
applies to both CLI and GUI runs and survives restarts.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, Field

from .models.finding import Finding

DEFAULT_PATH = "~/.redis-doctor/suppressions.db"

_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhdw])\s*$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(text: str) -> timedelta:
    """Parse a duration like '30m', '24h', '7d', '2w', '3600s'."""
    m = _DURATION_RE.match(text)
    if not m:
        raise ValueError(f"invalid duration: {text!r} (use e.g. 30m, 24h, 7d)")
    return timedelta(seconds=int(m.group(1)) * _UNIT_SECONDS[m.group(2).lower()])


class Suppression(BaseModel):
    id: int = 0
    finding_id: str
    affected: str | None = None
    target: str | None = None
    until: datetime
    reason: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def is_active(self, now: datetime | None = None) -> bool:
        return self.until > (now or datetime.now(UTC))

    def matches(self, finding: Finding, target: str | None) -> bool:
        if finding.id != self.finding_id:
            return False
        if self.target is not None and self.target != target:
            return False
        if self.affected is not None and self.affected not in (finding.affected or []):
            return False
        return True


def matches_any(
    finding: Finding,
    target: str | None,
    suppressions: list[Suppression],
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(UTC)
    return any(s.is_active(now) and s.matches(finding, target) for s in suppressions)


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class SuppressionStore:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS suppressions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    finding_id TEXT NOT NULL,
                    affected TEXT,
                    target TEXT,
                    until TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )

    def add(
        self,
        finding_id: str,
        until: datetime,
        *,
        affected: str | None = None,
        target: str | None = None,
        reason: str = "",
    ) -> Suppression:
        created = datetime.now(UTC)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO suppressions (finding_id, affected, target, until, reason, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (finding_id, affected, target, until.isoformat(), reason, created.isoformat()),
            )
            rid = int(cur.lastrowid)
        return Suppression(
            id=rid,
            finding_id=finding_id,
            affected=affected,
            target=target,
            until=until,
            reason=reason,
            created_at=created,
        )

    def _row(self, r: sqlite3.Row) -> Suppression:
        return Suppression(
            id=r["id"],
            finding_id=r["finding_id"],
            affected=r["affected"],
            target=r["target"],
            until=_parse_dt(r["until"]),
            reason=r["reason"],
            created_at=_parse_dt(r["created_at"]),
        )

    def list(self, active_only: bool = False) -> list[Suppression]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM suppressions ORDER BY id DESC").fetchall()
        items = [self._row(r) for r in rows]
        if active_only:
            now = datetime.now(UTC)
            items = [s for s in items if s.is_active(now)]
        return items

    def active(self) -> list[Suppression]:
        return self.list(active_only=True)

    def remove(self, suppression_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM suppressions WHERE id = ?", (suppression_id,))
            return cur.rowcount > 0

    def purge_expired(self) -> int:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM suppressions WHERE until <= ?", (now,))
            return cur.rowcount


def load_active(path: str) -> list[Suppression]:
    """Active suppressions, or [] if the store does not exist yet (cheap path)."""
    if not Path(path).expanduser().exists():
        return []
    return SuppressionStore(path).active()
