"""Health score (Section 10.2). Findings are primary; the score is a summary."""

from __future__ import annotations

from .models.finding import Category, Finding, Severity

CRITICAL_PENALTY = 15
WARNING_PENALTY = 5
INFO_PENALTY = 0

_PENALTY = {
    Severity.CRITICAL: CRITICAL_PENALTY,
    Severity.WARNING: WARNING_PENALTY,
    Severity.INFO: INFO_PENALTY,
}


def _score(findings: list[Finding]) -> int:
    score = 100
    for f in findings:
        score -= _PENALTY[f.severity]
    return max(0, min(100, score))


def health_score(findings: list[Finding]) -> int:
    return _score(findings)


def category_scores(findings: list[Finding]) -> dict[str, int]:
    """Per-category score. A category with no findings scores 100."""
    scores: dict[str, int] = {c.value: 100 for c in Category}
    by_cat: dict[str, list[Finding]] = {}
    for f in findings:
        by_cat.setdefault(f.category.value, []).append(f)
    for cat, fs in by_cat.items():
        scores[cat] = _score(fs)
    return scores
