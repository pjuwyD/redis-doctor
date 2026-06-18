# Web dashboard

A local web dashboard and JSON API built with FastAPI. Requires the `gui` extra:

```bash
pip install 'redis-doctor[gui]'
redis-doctor serve --host 127.0.0.1 --port 8787
```

It binds to `127.0.0.1` by default — **no data leaves the machine**. Passwords
entered for a run are used only for that request and are never persisted; the
stored report carries only the redacted target.

## Views

The single-page app (vanilla JS + Chart.js, no build step) offers:

- **Dashboard** — health-score, severity counts, an **Overview** (keys / streams /
  scripts / clients with a client-state bar / memory / hit-rate / ops-sec), a
  chart of only the categories that have findings, and the findings list with
  expand-for-detail and a per-finding mute button. When the report is persisted
  (always, for runs started from the GUI), an **Export: Markdown · PDF** bar links
  to the download endpoints.
- **Run** — enter a target and analyze live.
- **Explore** — browse keys read-only with metadata + bounded preview, and a lock
  to unlock full value reads. See the [Explore guide](explore.md).
- **History** — past reports (time, target, score, criticals); click to open, or
  use the per-row **MD** / **PDF** links to export.
- **Diff** — pick two reports and see the [diff](../commands/diff.md).
- **Suppressions** — list/add/remove muted findings; each Dashboard finding also
  has a **mute 24h** button. See [`suppress`](../commands/suppress.md).
- **Schedules** — create/list/delete cron schedules.
- **Fleet** — score cards for the instances configured via `--fleet` (below).

## JSON API

```text
POST   /api/analyze      { target, options }        -> Report JSON
GET    /api/reports                                  -> saved report metadata
GET    /api/reports/{id}                             -> one Report
GET    /api/diff?before={id}&after={id}              -> Diff JSON
POST   /api/schedule     { target, cron, notify }    -> create a schedule
GET    /api/schedule                                 -> list schedules
DELETE /api/schedule/{id}                            -> remove a schedule
GET    /api/export/{id}.md                           -> markdown report
GET    /api/export/{id}.pdf                           -> rendered PDF report
GET    /api/fleet                                    -> configured fleet cards
```

Example:

```bash
curl -s localhost:8787/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"target":"redis://localhost:6379","options":{}}' | jq .health_score
```

## History

Every run started from the dashboard is persisted to a SQLite database
(`~/.redis-doctor/history.db` by default, configurable via `history.path`) with the
full report plus indexable metadata. This is what powers the History and Diff
views, so the GUI records runs regardless of the `history.enabled` flag — that
flag only governs whether the **CLI** `analyze` writes to history. History
survives restarts; only the redacted target is stored, never a password.

## Scheduling

Schedules are backed by APScheduler. A schedule is `{ target, cron, notify }`; on
fire it runs the pipeline, saves to history, and notifies per the configured
channels. For unattended runs, prefer a Kubernetes CronJob or CI job calling
`analyze --fail-on critical` — see [CI integration](ci.md).

## Notifications

Configure Slack, email, or a generic webhook under `notify:` in the config. A run
notifies only when findings meet your `fail_on` threshold, and only via channels
you configured — never based on content discovered in Redis. See
[Safety](../safety.md).

## Fleet

The Fleet view shows one score card per instance you configure. Provide the list
when launching the server:

```bash
redis-doctor serve --fleet fleet.yml
```

```yaml
# fleet.yml
targets:
  - name: prod-cache
    url: redis://cache-1:6379
  - name: prod-queue
    url: redis://queue-1:6379
```

Each card shows the **latest stored health score** for that target (from
[history](#history), matched on the redacted target) and links to its latest
report. A card reads `–` until that target has been analyzed at least once — run
it from the **Run** view (or on a [schedule](#scheduling)) and the card fills in.
Without `--fleet`, the view explains how to configure one.

## PDF / Markdown export

From the **Dashboard**, the **Export** bar links to the markdown and PDF downloads
for the currently shown report. Directly, the endpoints are
`GET /api/export/{id}.md` and `GET /api/export/{id}.pdf`. PDF rendering uses
WeasyPrint, which needs native libraries — see
[Installation](../installation.md#weasyprint-system-libraries-pdf-export).
