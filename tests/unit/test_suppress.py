"""Finding suppression: store, matching, duration parsing, pipeline + GUI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from redis_doctor.config import Config
from redis_doctor.models.finding import Category, Finding, Severity
from redis_doctor.suppress import (
    Suppression,
    SuppressionStore,
    matches_any,
    parse_duration,
)


def _f(fid="memory.high_usage", affected=None, sev=Severity.WARNING):
    return Finding(
        id=fid,
        severity=sev,
        category=Category.MEMORY,
        title="t",
        affected=affected or [],
    )


# --- duration -------------------------------------------------------------


def test_parse_duration():
    assert parse_duration("30m") == timedelta(minutes=30)
    assert parse_duration("24h") == timedelta(hours=24)
    assert parse_duration("7d") == timedelta(days=7)
    assert parse_duration("2w") == timedelta(weeks=2)
    assert parse_duration("3600s") == timedelta(seconds=3600)
    with pytest.raises(ValueError):
        parse_duration("soon")


# --- matching -------------------------------------------------------------


def _supp(**kw):
    kw.setdefault("until", datetime.now(UTC) + timedelta(hours=1))
    return Suppression(**kw)


def test_match_by_id():
    s = _supp(finding_id="memory.high_usage")
    assert s.matches(_f("memory.high_usage"), "redis://x")
    assert not s.matches(_f("clients.idle_many"), "redis://x")


def test_match_scoped_to_affected():
    s = _supp(finding_id="bigkey.big_memory", affected="user:1")
    assert s.matches(_f("bigkey.big_memory", affected=["user:1"]), "redis://x")
    assert not s.matches(_f("bigkey.big_memory", affected=["user:2"]), "redis://x")


def test_match_scoped_to_target():
    s = _supp(finding_id="memory.high_usage", target="redis://prod/0")
    assert s.matches(_f(), "redis://prod/0")
    assert not s.matches(_f(), "redis://staging/0")


def test_expired_not_active():
    s = _supp(finding_id="x", until=datetime.now(UTC) - timedelta(minutes=1))
    assert not s.is_active()
    assert not matches_any(_f("x"), "t", [s])


# --- store ----------------------------------------------------------------


def test_store_add_list_active_remove(tmp_path):
    store = SuppressionStore(str(tmp_path / "s.db"))
    until = datetime.now(UTC) + timedelta(hours=2)
    s = store.add("memory.high_usage", until, affected="k", reason="ack")
    assert s.id >= 1
    assert len(store.list()) == 1
    assert len(store.active()) == 1
    # an expired one is excluded from active()
    store.add("clients.idle_many", datetime.now(UTC) - timedelta(seconds=1))
    assert len(store.list()) == 2
    assert len(store.active()) == 1
    assert store.remove(s.id) is True
    assert store.remove(9999) is False


def test_store_persists(tmp_path):
    path = str(tmp_path / "s.db")
    SuppressionStore(path).add("x", datetime.now(UTC) + timedelta(hours=1))
    assert len(SuppressionStore(path).list()) == 1


# --- pipeline filtering ---------------------------------------------------


def test_pipeline_splits_suppressed():
    from redis_doctor.pipeline import _apply_suppressions

    findings = [_f("memory.high_usage", sev=Severity.CRITICAL), _f("clients.idle_many")]
    supp = [_supp(finding_id="memory.high_usage")]
    kept, suppressed = _apply_suppressions(findings, "redis://x", supp)
    assert [f.id for f in kept] == ["clients.idle_many"]
    assert [f.id for f in suppressed] == ["memory.high_usage"]


def test_pipeline_no_suppressions_is_noop():
    from redis_doctor.pipeline import _apply_suppressions

    findings = [_f()]
    kept, suppressed = _apply_suppressions(findings, "redis://x", None)
    assert kept == findings and suppressed == []


# --- gui ------------------------------------------------------------------


def test_gui_suppression_crud(tmp_path):
    from fastapi.testclient import TestClient

    from redis_doctor.gui.server import create_app

    cfg = Config()
    cfg.history.path = str(tmp_path / "h.db")
    cfg.suppress.path = str(tmp_path / "s.db")
    client = TestClient(create_app(cfg))

    created = client.post(
        "/api/suppressions",
        json={"finding_id": "memory.high_usage", "for_seconds": 3600, "reason": "ack"},
    ).json()
    sid = created["id"]
    rows = client.get("/api/suppressions").json()
    assert any(r["id"] == sid and r["active"] for r in rows)
    client.delete(f"/api/suppressions/{sid}")
    assert all(r["id"] != sid for r in client.get("/api/suppressions").json())
