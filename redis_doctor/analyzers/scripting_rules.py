"""Scripting analyzer: Lua script cache + Redis Functions hygiene (Section 10)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.finding import Category, Confidence, Finding, Severity
from .base import Analyzer

if TYPE_CHECKING:
    from ..pipeline import RunContext


class ScriptingAnalyzer(Analyzer):
    name = "scripting"

    def analyze(self, ctx: RunContext) -> list[Finding]:
        data = ctx.collected.get("scripting")
        if data is None:
            return []

        th = ctx.config.thresholds
        findings: list[Finding] = []

        cached = data.get("cached_scripts", 0)
        if cached > th.cached_scripts_warning:
            findings.append(
                Finding(
                    id="scripting.many_cached_scripts",
                    severity=Severity.WARNING,
                    category=Category.SCRIPTING,
                    title=f"{cached:,} Lua scripts are cached",
                    explanation=(
                        "A large script cache uses memory, must be replicated to every "
                        "replica, and makes SCRIPT FLUSH riskier. It often means EVAL is "
                        "sent with inline bodies instead of reusing EVALSHA."
                    ),
                    evidence={"number_of_cached_scripts": cached},
                    suggested_checks=[
                        "redis-cli INFO memory | grep number_of_cached_scripts",
                    ],
                    suggested_fixes=[
                        "Reuse scripts via EVALSHA or migrate them to Functions",
                        "Avoid generating a new script body per request",
                    ],
                )
            )

        mem = data.get("scripts_memory", 0)
        limit = th.scripts_memory_warning_mb * 1024 * 1024
        if mem > limit:
            findings.append(
                Finding(
                    id="scripting.scripts_high_memory",
                    severity=Severity.WARNING,
                    category=Category.SCRIPTING,
                    title=f"Script/function memory is high ({mem / 1024 / 1024:.1f} MB)",
                    explanation=(
                        "The scripting subsystem is holding a lot of memory, usually a "
                        "symptom of a bloated script cache."
                    ),
                    evidence={"scripts_memory_bytes": mem},
                    suggested_checks=["redis-cli INFO memory | grep used_memory_scripts"],
                    suggested_fixes=["Reduce cached scripts; prefer EVALSHA/Functions"],
                )
            )

        running = data.get("running_script")
        if running:
            findings.append(
                Finding(
                    id="scripting.long_running_script",
                    severity=Severity.CRITICAL,
                    category=Category.SCRIPTING,
                    title=f"A script/function is currently running ({running})",
                    explanation=(
                        "Redis is single-threaded for command execution; a running "
                        "script blocks all other clients until it finishes."
                    ),
                    evidence={"running_script": running},
                    suggested_checks=["redis-cli FUNCTION STATS"],
                    suggested_fixes=[
                        "Investigate the long-running script",
                        "Keep scripts short; move heavy work off the server",
                    ],
                )
            )

        libs = data.get("libraries") or []
        if data.get("functions_supported") and (libs or data.get("functions_count")):
            findings.append(
                Finding(
                    id="scripting.functions_registered",
                    severity=Severity.INFO,
                    category=Category.SCRIPTING,
                    confidence=Confidence.HIGH,
                    title=(
                        f"{data.get('libraries_count', len(libs))} function "
                        f"librar{'y' if data.get('libraries_count', len(libs)) == 1 else 'ies'}, "
                        f"{data.get('functions_count', 0)} function(s) registered"
                    ),
                    explanation=(
                        "Registered Functions are server-side code. Listed here for "
                        "visibility; confirm each library is expected and current."
                    ),
                    evidence={
                        "libraries": [lib["name"] for lib in libs][:50],
                        "functions_count": data.get("functions_count", 0),
                    },
                    suggested_checks=["redis-cli FUNCTION LIST"],
                    suggested_fixes=["Audit registered libraries; remove unused ones"],
                    affected=[lib["name"] for lib in libs][:50],
                )
            )

        findings.extend(self._eval_inline(ctx, th))
        return findings

    def _eval_inline(self, ctx: RunContext, th) -> list[Finding]:
        slowlog = ctx.collected.get("slowlog")
        if not slowlog:
            return []
        entries = slowlog.get("entries", [])
        inline = sum(1 for e in entries if e.command == "EVAL")
        if inline >= th.eval_inline_warning:
            return [
                Finding(
                    id="scripting.eval_inline_repeated",
                    severity=Severity.WARNING,
                    category=Category.SCRIPTING,
                    title=f"Inline EVAL appears {inline}× in the slowlog",
                    explanation=(
                        "Repeated inline EVAL (vs EVALSHA) recompiles/caches a script "
                        "per call and bloats the script cache. Load once and call by SHA, "
                        "or use a Function."
                    ),
                    evidence={"eval_occurrences": inline},
                    suggested_checks=["redis-cli SLOWLOG GET 25"],
                    suggested_fixes=[
                        "Use SCRIPT LOAD + EVALSHA, or register a Function",
                    ],
                )
            ]
        return []
