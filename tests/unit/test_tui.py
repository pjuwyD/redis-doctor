"""TUI smoke tests using Textual's headless pilot."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from redis_doctor.models.finding import Category, Finding, Severity
from redis_doctor.models.report import Report, ReportSummary
from redis_doctor.tui.app import PANELS, RedisDoctorTUI


def _report() -> Report:
    return Report(
        target="redis://localhost:6379/0",
        generated_at=datetime.now(UTC),
        redis_doctor_version="1.0.0",
        health_score=70,
        summary=ReportSummary(critical=1, warning=1),
        findings=[
            Finding(
                id="memory.high_usage_noeviction",
                severity=Severity.CRITICAL,
                category=Category.MEMORY,
                title="usage high",
                explanation="why",
                evidence={"pct": 95},
                suggested_checks=["redis-cli INFO memory"],
                suggested_fixes=["increase maxmemory"],
            ),
            Finding(
                id="clients.idle_many",
                severity=Severity.WARNING,
                category=Category.CLIENTS,
                title="idle clients",
            ),
        ],
        stats={
            "keyspace": {
                "scanned": 10,
                "estimated_total": 10,
                "confidence": "high",
                "duration_seconds": 0.1,
                "complete": True,
                "type_distribution": {"string": 10},
                "top_prefixes_by_count": [{"prefix": "k", "count": 10, "memory_bytes": 100}],
                "top_prefixes_by_memory": [{"prefix": "k", "count": 10, "memory_bytes": 100}],
            },
            "clients": {
                "total": 5,
                "blocked": 0,
                "unnamed": 5,
                "idle_over_1h": 2,
                "top_commands": {},
            },
        },
    )


async def _wait_for_report(app, pilot, timeout=3.0) -> None:
    elapsed = 0.0
    while app.report is None and elapsed < timeout:
        await pilot.pause(0.05)
        elapsed += 0.05


def test_panels_render_without_error():
    """Every panel renders for both filtered and expanded views (no crash)."""
    report = _report()
    for _name, render in PANELS:
        for sev in (None, Severity.CRITICAL, Severity.WARNING):
            for expanded in (False, True):
                assert render(report, sev, expanded) is not None


def test_tui_mounts_and_interactions(tmp_path):
    report = _report()

    async def scenario():
        app = RedisDoctorTUI(lambda: report, target="redis://localhost:6379/0")
        async with app.run_test() as pilot:
            await _wait_for_report(app, pilot)
            assert app.report is not None  # Health panel populated from the report

            # f cycles the severity filter
            await pilot.press("f")
            await pilot.pause()
            assert app.filter_index == 1

            # e toggles expanded detail
            await pilot.press("e")
            await pilot.pause()
            assert app.expanded is True

            # switch panels
            app.panel_index = 2
            app.refresh_content()
            await pilot.pause()

            # s saves valid JSON
            path = tmp_path / "report.json"
            app.save_to(str(path))
            data = json.loads(path.read_text())
            assert data["health_score"] == 70

            # r re-runs analysis
            await pilot.press("r")
            await _wait_for_report(app, pilot)
            assert app.report is not None

    asyncio.run(scenario())


def test_tui_rerun_uses_fresh_report():
    reports = [_report(), _report()]
    reports[1].health_score = 42
    calls = {"n": 0}

    def run_analysis():
        r = reports[min(calls["n"], 1)]
        calls["n"] += 1
        return r

    async def scenario():
        app = RedisDoctorTUI(run_analysis, target="x")
        async with app.run_test() as pilot:
            await _wait_for_report(app, pilot)
            await pilot.press("r")
            # wait for the second analysis
            elapsed = 0.0
            while app.report.health_score != 42 and elapsed < 3.0:
                await pilot.pause(0.05)
                elapsed += 0.05
            assert app.report.health_score == 42

    asyncio.run(scenario())
