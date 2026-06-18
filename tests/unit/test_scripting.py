"""Scripting module: safety carve-outs + analyzer findings."""

from __future__ import annotations

import pytest

from redis_doctor import safety
from redis_doctor.analyzers.scripting_rules import ScriptingAnalyzer
from redis_doctor.config import Config
from redis_doctor.errors import UnsafeCommandError
from redis_doctor.models.finding import Severity
from redis_doctor.models.slowlog import SlowlogEntry

# --- safety ---------------------------------------------------------------


def test_read_only_script_and_function_subcommands_allowed():
    safety.check_command("SCRIPT", "EXISTS", "abc")
    safety.check_command("FUNCTION", "LIST")
    safety.check_command("FUNCTION", "STATS")


def test_mutating_script_and_function_subcommands_blocked():
    for cmd, sub in [
        ("SCRIPT", "LOAD"),
        ("SCRIPT", "FLUSH"),
        ("SCRIPT", "KILL"),
        ("FUNCTION", "LOAD"),
        ("FUNCTION", "DELETE"),
        ("FUNCTION", "FLUSH"),
        ("FUNCTION", "RESTORE"),
    ]:
        with pytest.raises(UnsafeCommandError):
            safety.check_command(cmd, sub, "x")
        safety.check_command(cmd, sub, "x", allow_write=True)  # unlocked -> ok


def test_eval_still_blocked():
    for cmd in ("EVAL", "EVALSHA", "FCALL"):
        with pytest.raises(UnsafeCommandError):
            safety.check_command(cmd, "body", 0)


# --- analyzer -------------------------------------------------------------


@pytest.fixture
def ctx(safe_fake):
    from redis_doctor.pipeline import RunContext

    return RunContext(redis=safe_fake, config=Config())


def _ids(findings):
    return {f.id: f for f in findings}


def test_many_cached_and_high_memory(ctx):
    ctx.config.thresholds.cached_scripts_warning = 100
    ctx.config.thresholds.scripts_memory_warning_mb = 1
    ctx.collected["scripting"] = {
        "cached_scripts": 5000,
        "scripts_memory": 5 * 1024 * 1024,
        "running_script": None,
        "functions_supported": True,
        "libraries": [],
        "libraries_count": 0,
        "functions_count": 0,
    }
    f = _ids(ScriptingAnalyzer().analyze(ctx))
    assert "scripting.many_cached_scripts" in f
    assert "scripting.scripts_high_memory" in f


def test_long_running_script_is_critical(ctx):
    ctx.collected["scripting"] = {"cached_scripts": 0, "running_script": "rdlib:rd_echo"}
    f = _ids(ScriptingAnalyzer().analyze(ctx))
    assert f["scripting.long_running_script"].severity == Severity.CRITICAL


def test_functions_registered_info(ctx):
    ctx.collected["scripting"] = {
        "cached_scripts": 0,
        "running_script": None,
        "functions_supported": True,
        "libraries": [{"name": "rdlib", "functions": ["rd_echo"]}],
        "libraries_count": 1,
        "functions_count": 1,
    }
    f = _ids(ScriptingAnalyzer().analyze(ctx))
    assert f["scripting.functions_registered"].severity == Severity.INFO
    assert "rdlib" in f["scripting.functions_registered"].affected


def test_eval_inline_repeated_from_slowlog(ctx):
    ctx.config.thresholds.eval_inline_warning = 3
    ctx.collected["scripting"] = {"cached_scripts": 0, "running_script": None}
    ctx.collected["slowlog"] = {
        "entries": [SlowlogEntry(id=i, command="EVAL", args=["return 1"]) for i in range(4)]
    }
    f = _ids(ScriptingAnalyzer().analyze(ctx))
    assert "scripting.eval_inline_repeated" in f


def test_no_findings_on_clean_instance(ctx):
    ctx.collected["scripting"] = {
        "cached_scripts": 2,
        "scripts_memory": 1000,
        "running_script": None,
        "functions_supported": True,
        "libraries": [],
        "libraries_count": 0,
        "functions_count": 0,
    }
    assert ScriptingAnalyzer().analyze(ctx) == []
