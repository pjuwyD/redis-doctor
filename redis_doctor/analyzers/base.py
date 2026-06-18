"""Analyzer ABC. Turns collected data into Findings.

Analyzers do not hardcode enable/disable or ignore logic; the pipeline filters
emitted findings through the rule engine. Thresholds come from config, or from
the rule engine for per-rule overrides.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..models.finding import Finding

if TYPE_CHECKING:
    from ..pipeline import RunContext


class Analyzer(ABC):
    name: str = "analyzer"

    @abstractmethod
    def analyze(self, ctx: RunContext) -> list[Finding]:
        """Return findings derived from data already collected in ctx."""
