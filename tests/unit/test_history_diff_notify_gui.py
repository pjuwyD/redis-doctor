"""History store, report diff, notifications, PDF export, and the GUI API."""

from __future__ import annotations

from datetime import UTC, datetime

from redis_doctor.config import Config, NotifyConfig
from redis_doctor.history.diff import diff_reports, render_diff_text
from redis_doctor.history.store import HistoryStore
from redis_doctor.models.finding import Category, Finding, Severity
from redis_doctor.models.report import Report, ReportSummary
from redis_doctor.models.server import ServerInfo


def _report(score=70, findings=None, used_memory=1000, stats=None) -> Report:
    findings = findings or []
    summary = ReportSummary()
    for f in findings:
        if f.severity == Severity.CRITICAL:
            summary.critical += 1
        elif f.severity == Severity.WARNING:
            summary.warning += 1
        else:
            summary.info += 1
    return Report(
        target="redis://localhost:6379/0",
        generated_at=datetime.now(UTC),
        redis_doctor_version="1.0.0",
        health_score=score,
        summary=summary,
        server=ServerInfo(used_memory_bytes=used_memory, total_keys=10),
        findings=findings,
        stats=stats or {},
    )


def _crit():
    return Finding(
        id="memory.high_usage_noeviction",
        severity=Severity.CRITICAL,
        category=Category.MEMORY,
        title="mem high",
    )


# --- history --------------------------------------------------------------


def test_history_save_list_get(tmp_path):
    store = HistoryStore(str(tmp_path / "h.db"))
    rid = store.save(_report(score=80))
    assert rid >= 1
    listed = store.list()
    assert len(listed) == 1
    assert listed[0]["health_score"] == 80
    fetched = store.get(rid)
    assert fetched is not None
    assert fetched.health_score == 80


def test_history_persists_across_instances(tmp_path):
    path = str(tmp_path / "h.db")
    HistoryStore(path).save(_report())
    assert len(HistoryStore(path).list()) == 1


# --- diff -----------------------------------------------------------------


def test_diff_added_removed_and_metrics():
    before = _report(score=85, findings=[], used_memory=1000)
    after = _report(score=70, findings=[_crit()], used_memory=2000)
    d = diff_reports(before, after)
    assert d.score_delta == -15
    assert any(f.id == "memory.high_usage_noeviction" for f in d.added)
    assert d.metric_deltas["used_memory_bytes"]["delta"] == 1000
    text = render_diff_text(d)
    assert "health score 85 -> 70" in text
    assert "new finding" in text


def test_diff_resolved_finding():
    before = _report(findings=[_crit()])
    after = _report(findings=[])
    d = diff_reports(before, after)
    assert any(f.id == "memory.high_usage_noeviction" for f in d.removed)


def test_diff_stream_growth():
    before = _report(stats={"streams": [{"name": "s", "length": 100, "groups": []}]})
    after = _report(stats={"streams": [{"name": "s", "length": 1100, "groups": []}]})
    d = diff_reports(before, after)
    assert d.metric_deltas["stream_length_changes"]["s"] == 1000


# --- notify ---------------------------------------------------------------


def test_notify_respects_threshold():
    from redis_doctor import notify as notify_mod

    sent = []
    cfg = NotifyConfig(slack_webhook_url="http://x")
    # clean report -> nothing sent
    assert notify_mod.notify(_report(findings=[]), cfg, "critical") == []

    # patch slack.send to record
    orig = notify_mod.slack.send
    notify_mod.slack.send = lambda url, report: sent.append(url)
    try:
        out = notify_mod.notify(_report(findings=[_crit()]), cfg, "critical")
    finally:
        notify_mod.slack.send = orig
    assert out == ["slack"]
    assert sent == ["http://x"]


def test_slack_payload_redacts_nothing_extra():
    from redis_doctor.notify.slack import build_payload

    payload = build_payload(_report(findings=[_crit()]))
    assert "text" in payload
    assert "mem high" in payload["text"]


# --- pdf ------------------------------------------------------------------


def test_pdf_render(tmp_path):
    from redis_doctor.output.pdf import render_pdf

    out = tmp_path / "r.pdf"
    render_pdf(_report(findings=[_crit()]), str(out))
    assert out.exists()
    assert out.read_bytes()[:4] == b"%PDF"


# --- gui api --------------------------------------------------------------


def test_gui_api_endpoints(tmp_path):
    from fastapi.testclient import TestClient

    from redis_doctor.gui.server import create_app

    cfg = Config()
    cfg.history.path = str(tmp_path / "h.db")
    app = create_app(cfg, fleet=[{"name": "n1", "target": "redis://x", "score": 90}])
    client = TestClient(app)

    # seed history directly so reports endpoints have data
    store = HistoryStore(cfg.history.path)
    r1 = store.save(_report(score=85))
    r2 = store.save(_report(score=60, findings=[_crit()]))

    assert client.get("/api/reports").json()[0]["id"] in (r1, r2)
    assert client.get(f"/api/reports/{r1}").json()["health_score"] == 85
    assert client.get("/api/reports/99999").status_code == 404

    diff = client.get(f"/api/diff?before={r1}&after={r2}").json()
    assert diff["score_delta"] == -25

    md = client.get(f"/api/export/{r1}.md")
    assert md.status_code == 200
    assert "Redis Doctor Report" in md.text

    fleet = client.get("/api/fleet").json()
    assert fleet[0]["name"] == "n1"

    assert client.get("/").status_code == 200


def test_gui_schedule_crud(tmp_path):
    from fastapi.testclient import TestClient

    from redis_doctor.gui.server import create_app

    cfg = Config()
    cfg.history.path = str(tmp_path / "h.db")
    client = TestClient(create_app(cfg))

    created = client.post(
        "/api/schedule", json={"target": "redis://x", "cron": "0 * * * *", "notify": False}
    ).json()
    sid = created["id"]
    assert any(s["id"] == sid for s in client.get("/api/schedule").json())
    client.delete(f"/api/schedule/{sid}")
    assert all(s["id"] != sid for s in client.get("/api/schedule").json())


def test_gui_analyze_persists_to_history(tmp_path, monkeypatch):
    """POST /api/analyze must record every run so History and Diff work in the GUI,
    regardless of the (CLI-only) history.enabled flag."""
    from fastapi.testclient import TestClient

    from redis_doctor.gui import server as srv

    # Avoid a real Redis: each run returns a synthetic report with a moving score.
    scores = iter([85, 60])
    monkeypatch.setattr(
        srv, "analyze_target", lambda target, cfg, suppressions=None: _report(score=next(scores))
    )

    cfg = Config()  # history.enabled stays False — the GUI persists anyway
    cfg.history.path = str(tmp_path / "h.db")
    client = TestClient(srv.create_app(cfg))

    r1 = client.post("/api/analyze", json={"target": "redis://x", "options": {}}).json()
    r2 = client.post("/api/analyze", json={"target": "redis://x", "options": {}}).json()
    assert "id" in r1 and "id" in r2

    rows = client.get("/api/reports").json()
    assert len(rows) == 2

    diff = client.get(f"/api/diff?before={r1['id']}&after={r2['id']}").json()
    assert diff["score_delta"] == -25


def test_gui_fleet_shows_latest_score(tmp_path):
    from fastapi.testclient import TestClient

    from redis_doctor.gui.server import create_app

    cfg = Config()
    cfg.history.path = str(tmp_path / "h.db")
    fleet = [
        {"name": "prod", "target": "redis://localhost:6379/0"},
        {"name": "never-run", "target": "redis://other:6379/0"},
    ]
    app = create_app(cfg, fleet=fleet)
    client = TestClient(app)

    # Persist a report whose target matches the first fleet entry.
    store = HistoryStore(cfg.history.path)
    rid = store.save(_report(score=42))  # target == redis://localhost:6379/0

    cards = {c["name"]: c for c in client.get("/api/fleet").json()}
    assert cards["prod"]["score"] == 42
    assert cards["prod"]["report_id"] == rid
    assert cards["never-run"]["score"] is None
    assert cards["never-run"]["report_id"] is None


def test_gui_analyze_connection_error_is_clean_json(tmp_path, monkeypatch):
    """A failing target returns a 400 with a JSON detail, not an opaque 500."""
    from fastapi.testclient import TestClient

    from redis_doctor.errors import ConnectionError as RDConnectionError
    from redis_doctor.gui import server as srv

    def boom(target, cfg, suppressions=None):
        raise RDConnectionError("Could not connect to redis://x/0: refused")

    monkeypatch.setattr(srv, "analyze_target", boom)
    cfg = Config()
    cfg.history.path = str(tmp_path / "h.db")
    client = TestClient(srv.create_app(cfg), raise_server_exceptions=False)

    resp = client.post("/api/analyze", json={"target": "redis://x", "options": {}})
    assert resp.status_code == 400
    body = resp.json()  # must be valid JSON
    assert "Could not connect" in body["detail"]


def test_gui_pdf_export(tmp_path):
    from fastapi.testclient import TestClient

    from redis_doctor.gui.server import create_app

    cfg = Config()
    cfg.history.path = str(tmp_path / "h.db")
    client = TestClient(create_app(cfg))
    rid = HistoryStore(cfg.history.path).save(_report(findings=[_crit()]))

    resp = client.get(f"/api/export/{rid}.pdf")
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


def test_load_fleet_parsing(tmp_path):
    from redis_doctor.gui.server import load_fleet

    f = tmp_path / "fleet.yml"
    f.write_text(
        "targets:\n  - name: cache\n    url: redis://:secret@cache:6379/1\n  - redis://queue:6379\n"
    )
    entries = load_fleet(str(f))
    assert entries[0]["name"] == "cache"
    assert "secret" not in entries[0]["target"]  # redacted
    assert entries[1]["name"] == "redis://queue:6379"  # bare url used as name
    assert entries[1]["target"].startswith("redis://queue:6379")
