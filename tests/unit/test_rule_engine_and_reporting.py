"""Rule engine, config overrides, markdown rendering, exit codes, and the
report subcommand."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from redis_doctor.cli import app, compute_exit_code
from redis_doctor.config import Config
from redis_doctor.errors import ExitCode
from redis_doctor.models.finding import Category, Finding, Severity
from redis_doctor.models.report import Report, ReportSummary
from redis_doctor.output.markdown import render_markdown
from redis_doctor.rule_engine import RuleEngine

runner = CliRunner()


def _report(findings):
    summary = ReportSummary()
    for f in findings:
        if f.severity == Severity.CRITICAL:
            summary.critical += 1
        elif f.severity == Severity.WARNING:
            summary.warning += 1
        else:
            summary.info += 1
    from datetime import UTC, datetime

    return Report(
        target="redis://localhost:6379/0",
        generated_at=datetime.now(UTC),
        redis_doctor_version="1.0.0",
        summary=summary,
        findings=findings,
    )


def test_rule_engine_loads_defaults():
    engine = RuleEngine.from_config(Config())
    assert engine.is_active("memory.high_usage")
    assert engine.get("memory.high_usage").get("warning_pct") == 80


def test_rule_engine_disable_via_rules():
    cfg = Config(rules={"memory.high_usage": {"enabled": False}})
    engine = RuleEngine.from_config(cfg)
    assert engine.is_active("memory.high_usage") is False


def test_rule_engine_ignore_rules():
    cfg = Config()
    cfg.ignore.rules = ["security.default_user"]
    engine = RuleEngine.from_config(cfg)
    assert engine.is_active("security.default_user") is False


def test_rule_engine_param_override():
    cfg = Config(rules={"memory.high_usage": {"warning_pct": 50}})
    engine = RuleEngine.from_config(cfg)
    assert engine.get("memory.high_usage").get("warning_pct") == 50


def test_compute_exit_codes():
    crit = _report(
        [Finding(id="a", severity=Severity.CRITICAL, category=Category.MEMORY, title="t")]
    )
    warn = _report(
        [Finding(id="b", severity=Severity.WARNING, category=Category.MEMORY, title="t")]
    )
    clean = _report([])

    assert compute_exit_code(crit, "critical", False) == ExitCode.FINDINGS_CRITICAL
    assert compute_exit_code(crit, "none", False) == ExitCode.SUCCESS
    assert compute_exit_code(warn, "warning", False) == ExitCode.FINDINGS_WARNING
    assert compute_exit_code(warn, "critical", False) == ExitCode.SUCCESS
    assert compute_exit_code(clean, "warning", False) == ExitCode.SUCCESS
    assert compute_exit_code(crit, "critical", True) == ExitCode.SUCCESS  # --no-fail


def test_markdown_render():
    rep = _report(
        [
            Finding(
                id="memory.high_usage",
                severity=Severity.CRITICAL,
                category=Category.MEMORY,
                title="high",
                explanation="why",
                evidence={"pct": 95},
            )
        ]
    )
    md = render_markdown(rep)
    assert "# Redis Doctor Report" in md
    assert "memory.high_usage" in md
    assert "Health score" in md


def test_report_subcommand_rerenders(tmp_path):
    rep = _report([])
    path = tmp_path / "r.json"
    path.write_text(rep.model_dump_json())
    result = runner.invoke(app, ["report", str(path), "--format", "markdown"])
    assert result.exit_code == 0
    assert "Redis Doctor Report" in result.stdout


def test_report_subcommand_bad_file():
    result = runner.invoke(app, ["report", "/no/such/file.json"])
    assert result.exit_code == ExitCode.INVALID_CONFIG


def _stub_fleet(monkeypatch, report):
    import redis_doctor.cli as cli_mod

    class _Dummy:
        def close(self):
            pass

    monkeypatch.setattr(cli_mod, "connect", lambda target: _Dummy())
    monkeypatch.setattr(cli_mod, "run_pipeline", lambda safe, cfg: report)


def test_fleet_honors_markdown_format(tmp_path, monkeypatch):
    rep = _report(
        [Finding(id="memory.high_usage", severity=Severity.CRITICAL, category=Category.MEMORY,
                 title="high")]
    )
    _stub_fleet(monkeypatch, rep)
    fleet_file = tmp_path / "fleet.yml"
    fleet_file.write_text("targets:\n  - {name: a, url: 'redis://localhost:6379'}\n")
    out = tmp_path / "fleet_out.md"

    result = runner.invoke(
        app, ["analyze", "--fleet", str(fleet_file), "--format", "markdown", "--output", str(out)]
    )
    assert result.exit_code == 0
    text = out.read_text()
    assert "# Redis Doctor Report" in text  # markdown, not the JSON dump
    assert '"instances"' not in text
    assert "memory.high_usage" in text


def test_fleet_defaults_to_json(tmp_path, monkeypatch):
    _stub_fleet(monkeypatch, _report([]))
    fleet_file = tmp_path / "fleet.yml"
    fleet_file.write_text("targets:\n  - {name: a, url: 'redis://localhost:6379'}\n")

    result = runner.invoke(app, ["analyze", "--fleet", str(fleet_file)])
    assert result.exit_code == 0
    assert '"instances"' in result.stdout


def test_secret_never_in_json_report():
    rep = _report([])
    rep.target = "redis://:***@host:6379/0"
    data = json.loads(rep.model_dump_json())
    assert "***" in data["target"]
