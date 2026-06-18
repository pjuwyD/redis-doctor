"""Persistence analyzer (Section 9.12)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ..models.finding import Category, Confidence, Finding, Severity
from .base import Analyzer

if TYPE_CHECKING:
    from ..pipeline import RunContext

LAST_SAVE_OLD_SECONDS = 3600
LAST_SAVE_OLD_CHANGES = 10000


def _int(d: dict, key: str, default: int = 0) -> int:
    try:
        return int(d.get(key, default))
    except (ValueError, TypeError):
        return default


class PersistenceAnalyzer(Analyzer):
    name = "persistence"

    def analyze(self, ctx: RunContext) -> list[Finding]:
        data = ctx.collected.get("persistence")
        if data is None:
            return []

        findings: list[Finding] = []

        if str(data.get("rdb_last_bgsave_status", "ok")).lower() not in ("ok", ""):
            findings.append(
                Finding(
                    id="persistence.rdb_failed",
                    severity=Severity.CRITICAL,
                    category=Category.PERSISTENCE,
                    title="The last RDB background save failed",
                    explanation=(
                        "A failed RDB save means recent data is not persisted to disk "
                        "and would be lost on restart."
                    ),
                    evidence={"rdb_last_bgsave_status": data.get("rdb_last_bgsave_status")},
                    suggested_checks=[
                        "redis-cli INFO persistence | grep rdb_last_bgsave_status",
                        "Check disk space and permissions on the dump directory",
                    ],
                    suggested_fixes=["Resolve disk/permission errors", "Verify BGSAVE succeeds"],
                )
            )

        aof_bgrewrite = str(data.get("aof_last_bgrewrite_status", "ok")).lower()
        aof_write = str(data.get("aof_last_write_status", "ok")).lower()
        if (aof_bgrewrite not in ("ok", "")) or (aof_write not in ("ok", "")):
            findings.append(
                Finding(
                    id="persistence.aof_failed",
                    severity=Severity.CRITICAL,
                    category=Category.PERSISTENCE,
                    title="An AOF write or rewrite failed",
                    explanation=(
                        "AOF errors mean the append-only log is not durable; writes "
                        "since the failure may be lost."
                    ),
                    evidence={
                        "aof_last_bgrewrite_status": data.get("aof_last_bgrewrite_status"),
                        "aof_last_write_status": data.get("aof_last_write_status"),
                    },
                    suggested_checks=["redis-cli INFO persistence | grep aof"],
                    suggested_fixes=["Check disk space and the AOF directory"],
                )
            )

        if _int(data, "loading") == 1:
            findings.append(
                Finding(
                    id="persistence.loading",
                    severity=Severity.CRITICAL,
                    category=Category.PERSISTENCE,
                    title="Redis is loading a dataset from disk",
                    explanation=(
                        "While loading, Redis blocks most commands and is not fully available."
                    ),
                    evidence={"loading": 1},
                    suggested_checks=["redis-cli INFO persistence | grep loading"],
                    suggested_fixes=["Wait for loading to complete"],
                )
            )

        # none_enabled depends on CONFIG (save / appendonly).
        values = ctx.collected.get("config_values") or {}
        rdb_enabled = bool(str(values.get("save", "")).strip())
        aof_enabled = str(values.get("appendonly", "no")).lower() == "yes"
        if values and not rdb_enabled and not aof_enabled:
            findings.append(
                Finding(
                    id="persistence.none_enabled",
                    severity=Severity.WARNING,
                    category=Category.PERSISTENCE,
                    confidence=Confidence.MEDIUM,
                    title="No persistence is enabled",
                    explanation=(
                        "Neither RDB nor AOF is enabled. Acceptable for a pure cache, "
                        "but all data is lost on restart."
                    ),
                    evidence={
                        "save": values.get("save", ""),
                        "appendonly": values.get("appendonly"),
                    },
                    suggested_checks=[
                        "redis-cli CONFIG GET save",
                        "redis-cli CONFIG GET appendonly",
                    ],
                    suggested_fixes=["Enable RDB and/or AOF if the data must survive restarts"],
                )
            )

        changes = _int(data, "rdb_changes_since_last_save")
        last_save = _int(data, "rdb_last_save_time")
        age = int(time.time()) - last_save if last_save else 0
        if changes >= LAST_SAVE_OLD_CHANGES and age >= LAST_SAVE_OLD_SECONDS:
            findings.append(
                Finding(
                    id="persistence.last_save_old",
                    severity=Severity.WARNING,
                    category=Category.PERSISTENCE,
                    confidence=Confidence.MEDIUM,
                    title="Last successful save is old with many pending changes",
                    explanation=(
                        "Many changes accumulated since the last save means a large "
                        "window of data would be lost on a crash."
                    ),
                    evidence={"rdb_changes_since_last_save": changes, "seconds_since_save": age},
                    suggested_checks=["redis-cli INFO persistence"],
                    suggested_fixes=["Trigger/confirm BGSAVE", "Review the save schedule"],
                )
            )

        return findings
