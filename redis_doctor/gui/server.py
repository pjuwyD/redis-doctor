"""FastAPI web GUI + JSON API (Section 12).

Binds to localhost by default; no data leaves the machine. Passwords supplied in
a request are used only for that request and never persisted — the stored report
carries only the redacted target.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import Config
from ..connection import connect, parse_target
from ..errors import RedisDoctorError
from ..history.diff import diff_reports
from ..history.store import HistoryStore
from ..models.report import Report
from ..output.markdown import render_markdown
from ..pipeline import run_pipeline

STATIC_DIR = Path(__file__).parent / "static"


class AnalyzeRequest(BaseModel):
    target: str
    options: dict[str, Any] = {}


class ScheduleRequest(BaseModel):
    target: str
    cron: str
    notify: bool = False


class ScanRequest(BaseModel):
    target: str
    match: str | None = None
    cursor: int = 0
    count: int = 500
    db: int | None = None


class KeyRequest(BaseModel):
    target: str
    key: str = ""
    full: bool = False
    db: int | None = None


class SuppressRequest(BaseModel):
    finding_id: str
    for_seconds: int = 86400
    affected: str | None = None
    target: str | None = None
    reason: str = ""


def analyze_target(target_url: str, config: Config, suppressions: list | None = None) -> Report:
    target = parse_target(target_url)
    safe = connect(target)
    try:
        return run_pipeline(safe, config, suppressions=suppressions)
    finally:
        safe.close()


def create_app(config: Config | None = None, fleet: list[dict] | None = None) -> FastAPI:
    from ..suppress import SuppressionStore

    cfg = config or Config()
    store = HistoryStore(cfg.history.path)
    suppress_store = SuppressionStore(cfg.suppress.path)
    app = FastAPI(title="redis-doctor")
    schedules: dict[str, dict] = {}
    scheduler = _make_scheduler()

    @app.exception_handler(RedisDoctorError)
    def _on_doctor_error(_request: Request, exc: RedisDoctorError) -> JSONResponse:
        # Connection/auth/config failures become a clean JSON error (e.g. a bad
        # target), not an opaque 500, so the UI can show the real reason.
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    def _run_and_store(target: str, do_notify: bool) -> Report:
        report = analyze_target(target, cfg, suppress_store.active())
        store.save(report)
        if do_notify:
            from ..notify import notify as send_notify

            send_notify(report, cfg.notify, cfg.output.fail_on or "warning")
        return report

    @app.post("/api/analyze")
    def api_analyze(req: AnalyzeRequest):
        report = analyze_target(req.target, cfg, suppress_store.active())
        # The dashboard's History and Diff views depend on persisted runs, so the
        # GUI always records to history (unlike the CLI, which honors
        # history.enabled). Only the redacted target is stored.
        report_id = store.save(report)
        payload = report.model_dump(mode="json")
        payload["id"] = report_id
        return JSONResponse(payload)

    @app.get("/api/reports")
    def api_reports():
        return store.list()

    @app.get("/api/trends")
    def api_trends():
        # Time series of key metrics per target, built from stored reports.
        return store.trends()

    @app.get("/api/reports/{report_id}")
    def api_report(report_id: int):
        report = store.get(report_id)
        if report is None:
            raise HTTPException(404, "report not found")
        return JSONResponse(report.model_dump(mode="json"))

    @app.get("/api/diff")
    def api_diff(before: int, after: int):
        b, a = store.get(before), store.get(after)
        if b is None or a is None:
            raise HTTPException(404, "report not found")
        return JSONResponse(diff_reports(b, a).model_dump(mode="json"))

    @app.post("/api/schedule")
    def api_schedule_create(req: ScheduleRequest):
        sid = uuid.uuid4().hex[:8]
        schedules[sid] = {"id": sid, "target": req.target, "cron": req.cron, "notify": req.notify}
        if scheduler is not None:
            from apscheduler.triggers.cron import CronTrigger

            scheduler.add_job(
                _run_and_store,
                CronTrigger.from_crontab(req.cron),
                args=[req.target, req.notify],
                id=sid,
            )
        return schedules[sid]

    @app.get("/api/schedule")
    def api_schedule_list():
        return list(schedules.values())

    @app.delete("/api/schedule/{sid}")
    def api_schedule_delete(sid: str):
        schedules.pop(sid, None)
        if scheduler is not None and scheduler.get_job(sid):
            scheduler.remove_job(sid)
        return {"deleted": sid}

    @app.get("/api/export/{report_id}.md")
    def api_export_md(report_id: int):
        report = store.get(report_id)
        if report is None:
            raise HTTPException(404, "report not found")
        return PlainTextResponse(render_markdown(report))

    @app.get("/api/export/{report_id}.pdf")
    def api_export_pdf(report_id: int):
        report = store.get(report_id)
        if report is None:
            raise HTTPException(404, "report not found")
        from ..output.pdf import render_pdf

        out = Path(cfg.history.path).expanduser().parent / f"report-{report_id}.pdf"
        render_pdf(report, str(out))
        return FileResponse(str(out), media_type="application/pdf")

    @app.get("/api/fleet")
    def api_fleet():
        # Each card shows the latest stored score for that target and links to its
        # latest report. Targets are matched on their redacted form.
        latest: dict[str, dict] = {}
        for row in store.list():  # newest-first
            latest.setdefault(row["target"], row)
        out = []
        for item in fleet or []:
            row = latest.get(item["target"])
            out.append(
                {
                    "name": item.get("name", item["target"]),
                    "target": item["target"],
                    "score": row["health_score"] if row else None,
                    "report_id": row["id"] if row else None,
                }
            )
        return out

    @app.post("/api/explore/scan")
    def api_explore_scan(req: ScanRequest):
        from ..explore import scan_page

        # `db` selects a specific logical DB (chosen at connect time; SELECT is
        # never issued). None keeps whatever the target URL specifies.
        safe = connect(parse_target(req.target, db=req.db))
        try:
            return scan_page(safe, match=req.match, cursor=req.cursor, count=req.count)
        finally:
            safe.close()

    @app.post("/api/explore/key")
    def api_explore_key(req: KeyRequest):
        from ..explore import key_detail

        # Full value reads require an unlocked connection; the lock is enforced at
        # the safety layer, not just in the UI.
        safe = connect(parse_target(req.target, db=req.db), allow_expensive=req.full)
        try:
            return key_detail(safe, req.key, full=req.full)
        finally:
            safe.close()

    @app.post("/api/explore/functions")
    def api_explore_functions(req: KeyRequest):
        from ..explore import function_overview

        # `full` includes Function source code (FUNCTION LIST WITHCODE) and needs
        # the same unlock as full value reads.
        safe = connect(parse_target(req.target, db=req.db), allow_expensive=req.full)
        try:
            return function_overview(safe, full=req.full)
        finally:
            safe.close()

    @app.get("/api/suppressions")
    def api_suppressions():
        return [
            s.model_dump(mode="json") | {"active": s.is_active()} for s in suppress_store.list()
        ]

    @app.post("/api/suppressions")
    def api_suppress_create(req: SuppressRequest):
        from datetime import UTC, datetime, timedelta

        until = datetime.now(UTC) + timedelta(seconds=max(1, req.for_seconds))
        s = suppress_store.add(
            req.finding_id,
            until,
            affected=req.affected,
            target=req.target,
            reason=req.reason,
        )
        return s.model_dump(mode="json")

    @app.delete("/api/suppressions/{suppression_id}")
    def api_suppress_delete(suppression_id: int):
        return {"deleted": suppress_store.remove(suppression_id), "id": suppression_id}

    @app.get("/", response_class=HTMLResponse)
    def index():
        idx = STATIC_DIR / "index.html"
        if not idx.exists():
            return HTMLResponse("<h1>redis-doctor</h1>")
        html = idx.read_text()
        # Cache-bust the static assets by file mtime so browsers always pick up a
        # changed app.js / styles.css instead of serving a stale cached copy.
        version = 0
        for name in ("app.js", "styles.css"):
            f = STATIC_DIR / name
            if f.exists():
                version = max(version, int(f.stat().st_mtime))
        html = html.replace("/static/app.js", f"/static/app.js?v={version}")
        html = html.replace("/static/styles.css", f"/static/styles.css?v={version}")
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    if scheduler is not None:
        scheduler.start()

    return app


def _make_scheduler():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        return BackgroundScheduler()
    except Exception:
        return None


def load_fleet(path: str) -> list[dict]:
    """Read a fleet YAML (`targets: [{name, url}, ...]`) into redacted entries."""
    import yaml

    spec = yaml.safe_load(Path(path).read_text()) or {}
    entries: list[dict] = []
    for e in spec.get("targets", []):
        url = e.get("url") if isinstance(e, dict) else e
        name = e.get("name", url) if isinstance(e, dict) else url
        entries.append({"name": name, "target": parse_target(url).redacted_url()})
    return entries


def serve(
    host: str = "127.0.0.1",
    port: int = 8787,
    config: Config | None = None,
    fleet: list[dict] | None = None,
) -> None:
    import uvicorn

    uvicorn.run(create_app(config or Config(), fleet=fleet), host=host, port=port)
