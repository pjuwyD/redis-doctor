"""Report, ReportSummary, SkippedModule — the top-level output document."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .finding import Finding
from .server import ServerInfo


class SkippedModule(BaseModel):
    module: str
    reason: str


class ReportSummary(BaseModel):
    critical: int = 0
    warning: int = 0
    info: int = 0


class Report(BaseModel):
    target: str
    generated_at: datetime
    redis_doctor_version: str
    duration_seconds: float = 0.0
    sampled: bool = False
    health_score: int = 100
    category_scores: dict[str, int] = Field(default_factory=dict)
    summary: ReportSummary = Field(default_factory=ReportSummary)
    server: ServerInfo = Field(default_factory=ServerInfo)
    findings: list[Finding] = Field(default_factory=list)
    suppressed: list[Finding] = Field(default_factory=list)
    skipped: list[SkippedModule] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
