from redis_doctor.models.finding import Category, Finding, Severity
from redis_doctor.scoring import category_scores, health_score


def _f(sev, cat=Category.SERVER):
    return Finding(id="x", severity=sev, category=cat, title="t")


def test_empty_is_100():
    assert health_score([]) == 100


def test_penalties():
    assert health_score([_f(Severity.CRITICAL)]) == 85
    assert health_score([_f(Severity.WARNING)]) == 95
    assert health_score([_f(Severity.INFO)]) == 100
    assert health_score([_f(Severity.CRITICAL), _f(Severity.WARNING)]) == 80


def test_clamped_to_zero():
    assert health_score([_f(Severity.CRITICAL)] * 10) == 0


def test_category_scores():
    findings = [_f(Severity.CRITICAL, Category.MEMORY), _f(Severity.WARNING, Category.CLIENTS)]
    scores = category_scores(findings)
    assert scores["memory"] == 85
    assert scores["clients"] == 95
    assert scores["streams"] == 100  # no findings -> 100
