"""Report history persistence (Section 13.1). SQLite-backed.

Stores the full Report JSON plus indexable metadata (time, redacted target,
score, summary counts). The redacted target is what is persisted — never a
password.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..models.report import Report

DEFAULT_PATH = "~/.redis-doctor/history.db"


def _trend_point(row: Any) -> dict[str, Any]:
    """Extract one time-series point from a stored report row."""
    point: dict[str, Any] = {
        "id": row["id"],
        "generated_at": row["generated_at"],
        "target": row["target"],
        "health_score": row["health_score"],
        "memory_bytes": None,
        "keys": None,
        "idle_clients": None,
        "stream_length": None,
    }
    try:
        stats = json.loads(row["report_json"]).get("stats") or {}
    except (ValueError, TypeError):
        return point
    ov = stats.get("overview") or {}
    if isinstance(ov.get("memory"), dict):
        point["memory_bytes"] = ov["memory"].get("used_bytes")
    if isinstance(ov.get("keys"), dict):
        point["keys"] = ov["keys"].get("total")
    if isinstance(ov.get("clients"), dict):
        point["idle_clients"] = ov["clients"].get("idle_over_1h")
    streams = stats.get("streams")
    if isinstance(streams, list):
        point["stream_length"] = sum(s.get("length", 0) for s in streams if isinstance(s, dict))
    return point


class HistoryStore:
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
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generated_at TEXT NOT NULL,
                    target TEXT NOT NULL,
                    health_score INTEGER NOT NULL,
                    critical INTEGER NOT NULL,
                    warning INTEGER NOT NULL,
                    info INTEGER NOT NULL,
                    report_json TEXT NOT NULL
                )
                """
            )

    def save(self, report: Report) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO reports
                    (generated_at, target, health_score, critical, warning, info, report_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.generated_at.isoformat(),
                    report.target,
                    report.health_score,
                    report.summary.critical,
                    report.summary.warning,
                    report.summary.info,
                    report.model_dump_json(),
                ),
            )
            return int(cur.lastrowid)

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, generated_at, target, health_score, critical, warning, info
                FROM reports ORDER BY id DESC
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def trends(self) -> list[dict[str, Any]]:
        """Time series of headline metrics per stored report, oldest first.

        Each point carries the metrics charted by the GUI History tab. Metrics
        are read from the stored report JSON (tolerant of missing fields on older
        rows) rather than a fixed set of columns.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, generated_at, target, health_score, report_json
                FROM reports ORDER BY id ASC
                """
            ).fetchall()
        return [_trend_point(r) for r in rows]

    def get(self, report_id: int) -> Report | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT report_json FROM reports WHERE id = ?", (report_id,)
            ).fetchone()
        if row is None:
            return None
        return Report.model_validate_json(row["report_json"])
