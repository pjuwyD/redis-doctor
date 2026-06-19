"""Rich terminal output: header, server summary, findings by severity, notes."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..models.finding import Finding, Severity
from ..models.report import Report

_SEVERITY_STYLE = {
    Severity.CRITICAL: "bold red",
    Severity.WARNING: "yellow",
    Severity.INFO: "dim",
}
_SEVERITY_LABEL = {
    Severity.CRITICAL: "Critical findings",
    Severity.WARNING: "Warnings",
    Severity.INFO: "Info",
}


def _plain(text: str) -> Text:
    """Wrap user-provided text so Rich never interprets it as markup or emoji."""
    return Text(text)


def human_bytes(n: int | None) -> str:
    if not n:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(n)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def human_duration(seconds: int) -> str:
    if seconds <= 0:
        return "0s"
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m and not d:
        parts.append(f"{m}m")
    return " ".join(parts) or f"{seconds}s"


def _score_style(score: int) -> str:
    if score >= 80:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"


def render(report: Report, console: Console | None = None) -> None:
    console = console or Console()
    s = report.server

    header = Text()
    header.append("Redis Doctor Report\n", style="bold")
    header.append(f"Target: {report.target}\n")
    header.append(f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
    header.append("Health score: ")
    header.append(f"{report.health_score}/100", style=f"bold {_score_style(report.health_score)}")
    console.print(header)

    identity = Text()
    identity.append(
        f"Redis {s.redis_version} ({s.redis_mode}) · role {s.role} · "
        f"uptime {human_duration(s.uptime_seconds)}"
    )
    console.print(Panel(identity, title="Server", expand=False))

    render_overview(report, console)
    render_keyspace(report, console)
    render_clients(report, console)
    render_streams(report, console)
    render_sentinel(report, console)
    render_cluster(report, console)

    counts = report.summary
    console.print(
        f"[red]{counts.critical} critical[/red]  "
        f"[yellow]{counts.warning} warning[/yellow]  "
        f"[dim]{counts.info} info[/dim]\n"
    )

    for severity in (Severity.CRITICAL, Severity.WARNING, Severity.INFO):
        group = [f for f in report.findings if f.severity == severity]
        if not group:
            continue
        console.print(f"[{_SEVERITY_STYLE[severity]}]{_SEVERITY_LABEL[severity]}:[/]")
        for f in group:
            _render_finding(console, f)
        console.print()

    if report.suppressed:
        ids = ", ".join(sorted({f.id for f in report.suppressed}))
        console.print(
            f"[dim]Suppressed: {len(report.suppressed)} finding(s) muted (not scored): {ids}[/dim]"
        )

    if report.skipped:
        console.print("[dim]Skipped:[/dim]")
        for sk in report.skipped:
            console.print(f"[dim]- {sk.module}: {sk.reason}[/dim]")


def render_overview(report: Report, console: Console | None = None) -> None:
    """At-a-glance totals shared with the TUI and GUI."""
    console = console or Console()
    table = overview_table(report.stats.get("overview"))
    if table is not None:
        console.print(table)
        console.print()


def overview_table(ov: dict | None) -> Table | None:
    """Build the at-a-glance Overview table (reused by the terminal and TUI)."""
    if not ov:
        return None
    table = Table(title="Overview", title_style="bold", expand=False, show_header=False, box=None)
    table.add_column("Metric", style="dim", justify="right")
    table.add_column("Value")

    keys = ov.get("keys")
    if keys:
        dist = ", ".join(
            f"{t} {c:,}" for t, c in sorted(keys["by_type"].items(), key=lambda x: -x[1])[:6]
        )
        sampled = "" if keys.get("complete") else f" (sampled {keys['sampled']:,})"
        val = f"{keys['total']:,}{sampled}"
        table.add_row("Keys", val + (f"   {dist}" if dist else ""))

    databases = ov.get("databases")
    if databases and len(databases) > 1:
        per_db = "  ".join(
            f"{d['db']} {d['keys']:,} ({d['no_ttl_pct']:.0f}% no TTL)" for d in databases[:8]
        )
        table.add_row("Databases", per_db)

    streams = ov.get("streams")
    if streams is not None:
        table.add_row("Streams", f"{streams['count']:,}  ({streams['total_pending']:,} pending)")

    scr = ov.get("scripting")
    if scr is not None:
        table.add_row(
            "Scripts / Functions",
            f"{scr['cached_scripts']:,} cached · {scr['functions']:,} functions "
            f"in {scr['libraries']:,} lib(s)",
        )

    cl = ov.get("clients")
    if cl:
        head = f"{cl['total']:,}"
        if cl.get("maxclients"):
            head += f" / {cl['maxclients']:,}"
        head += f" · {cl['blocked']} blocked"
        if cl.get("unnamed"):
            head += f" · {cl['unnamed']} unnamed"
        table.add_row("Clients", head)
        states = ", ".join(
            f"{n.replace('_', ' ')} {v}"
            for n, v in sorted((cl.get("states") or {}).items(), key=lambda x: -x[1])
        )
        if states:
            table.add_row("Client states", states)

    mem = ov.get("memory")
    if mem:
        if mem.get("pct") is not None:
            line = (
                f"{human_bytes(mem['used_bytes'])} / {human_bytes(mem['max_bytes'])} "
                f"({mem['pct']:.0f}%) · {mem['policy']}"
            )
        else:
            line = f"{human_bytes(mem['used_bytes'])} / unbounded · {mem['policy']}"
        table.add_row("Memory", line)

    srv = ov.get("server")
    if srv:
        thr = f"{srv['ops_per_sec']:,} ops/s"
        if srv.get("hit_rate") is not None:
            thr += f" · {srv['hit_rate']:.0f}% hit rate"
        if srv.get("evicted_keys"):
            thr += f" · {srv['evicted_keys']:,} evicted"
        table.add_row("Throughput", thr)

    sl = ov.get("slowlog")
    if sl:
        table.add_row("Slowlog", f"{sl['length']:,} entries")

    return table


def render_keyspace(report: Report, console: Console | None = None) -> None:
    """Print prefix-by-count and prefix-by-memory tables + sampling metadata."""
    console = console or Console()
    ks = report.stats.get("keyspace")
    if not ks:
        return

    meta = Text()
    meta.append("Key analysis based on sample:\n", style="bold")
    meta.append(
        f"- scanned {ks['scanned']:,} keys from estimated {ks['estimated_total']:,} total keys\n"
    )
    meta.append(f"- confidence: {ks['confidence']}\n")
    meta.append(f"- scan duration: {ks['duration_seconds']}s\n")
    meta.append(f"- complete scan: {'yes' if ks['complete'] else 'no (sampled)'}\n")
    console.print(meta)

    by_count = ks.get("top_prefixes_by_count") or []
    if by_count:
        table = Table(title="Top prefixes by count", title_style="bold", expand=False)
        table.add_column("#", justify="right")
        table.add_column("Prefix")
        table.add_column("Keys", justify="right")
        table.add_column("Share", justify="right")
        for i, p in enumerate(by_count, 1):
            share = p["count"] / ks["scanned"] if ks["scanned"] else 0
            table.add_row(str(i), _plain(f"{p['prefix']}:*"), f"{p['count']:,}", f"{share:.0%}")
        console.print(table)

    by_mem = ks.get("top_prefixes_by_memory") or []
    if by_mem and any(p["memory_bytes"] for p in by_mem):
        table = Table(title="Top prefixes by memory", title_style="bold", expand=False)
        table.add_column("#", justify="right")
        table.add_column("Prefix")
        table.add_column("Memory", justify="right")
        table.add_column("Keys", justify="right")
        for i, p in enumerate(by_mem, 1):
            table.add_row(
                str(i),
                _plain(f"{p['prefix']}:*"),
                human_bytes(p["memory_bytes"]),
                f"{p['count']:,}",
            )
        console.print(table)

    dist = ks.get("type_distribution") or {}
    if dist:
        total = sum(dist.values()) or 1
        parts = ", ".join(
            f"{t} {100 * c / total:.0f}%" for t, c in sorted(dist.items(), key=lambda x: -x[1])
        )
        console.print(f"Type distribution: {parts}\n")


def render_clients(report: Report, console: Console | None = None) -> None:
    console = console or Console()
    c = report.stats.get("clients")
    if not c:
        return
    body = Text()
    body.append(
        f"- {c['total']} connected, {c['blocked']} blocked, {c['idle_over_1h']} idle over 1h\n"
    )
    if c["total"]:
        body.append(f"- {c['unnamed'] / c['total']:.0%} of clients have no name set\n")
    if c.get("top_commands"):
        cmds = ", ".join(f"{k} {v}" for k, v in c["top_commands"].items())
        body.append(f"- Top client commands: {cmds}\n")
    console.print(Panel(body, title="Clients", expand=False))


def render_streams(report: Report, console: Console | None = None) -> None:
    console = console or Console()
    streams = report.stats.get("streams")
    if not streams:
        return
    table = Table(title="Streams", title_style="bold", expand=False)
    table.add_column("Stream")
    table.add_column("Length", justify="right")
    table.add_column("Group")
    table.add_column("Consumers", justify="right")
    table.add_column("Pending", justify="right")
    table.add_column("Lag", justify="right")
    for st in streams:
        if not st["groups"]:
            table.add_row(_plain(st["name"]), f"{st['length']:,}", "-", "-", "-", "-")
        for g in st["groups"]:
            table.add_row(
                _plain(st["name"]),
                f"{st['length']:,}",
                _plain(g["name"]),
                str(g["consumers"]),
                f"{g['pending']:,}",
                "-" if g["lag"] is None else f"{g['lag']:,}",
            )
    console.print(table)


def render_sentinel(report: Report, console: Console | None = None) -> None:
    console = console or Console()
    s = report.stats.get("sentinel")
    if not s:
        return
    body = Text()
    body.append(f"- Master: {s['master_name']}\n")
    body.append(
        f"- Sentinels: {s['reachable_sentinels']} reachable / "
        f"{s['configured_sentinels']} known, quorum {s['quorum']}\n"
    )
    if s.get("master_addrs"):
        body.append(f"- Master address(es): {', '.join(s['master_addrs'])}\n")
    body.append(f"- Replicas: {len(s.get('replicas', []))}\n")
    console.print(Panel(body, title="Sentinel", expand=False))


def render_cluster(report: Report, console: Console | None = None) -> None:
    console = console or Console()
    c = report.stats.get("cluster")
    if not c:
        return
    meta = Text()
    meta.append(
        f"Cluster state: {c['state']}; slots {c['slots_assigned']}/16384 assigned "
        f"({c['uncovered_slots']} uncovered); {c['known_nodes']} nodes, size {c['size']}\n"
    )
    console.print(meta)
    nodes = c.get("nodes") or []
    if nodes:
        table = Table(title="Cluster nodes", title_style="bold", expand=False)
        table.add_column("Node")
        table.add_column("Role")
        table.add_column("Slots", justify="right")
        table.add_column("Keys", justify="right")
        table.add_column("Memory", justify="right")
        table.add_column("Clients", justify="right")
        for n in nodes:
            table.add_row(
                _plain(n["addr"]),
                n["role"] + (" (fail)" if n.get("failed") else ""),
                str(n["slots"]),
                f"{n['keys']:,}",
                human_bytes(n["used_memory"]),
                str(n["clients"]),
            )
        console.print(table)


def _render_finding(console: Console, f: Finding) -> None:
    """Render one finding. User-derived text is appended as plain Text segments
    so key names containing `[` or `:shortcode:` are never interpreted."""
    style = _SEVERITY_STYLE[f.severity]
    head = Text("  ")
    head.append(f"[{f.category.value.upper()}] {f.id}", style=style)
    head.append(" — ")
    head.append(f.title)
    console.print(head)

    if f.evidence:
        ev = ", ".join(f"{k}={v}" for k, v in f.evidence.items())
        _detail(console, "Evidence", ev)
    if f.explanation:
        _detail(console, "Impact", f.explanation)
    if f.suggested_checks:
        _detail(console, "Checks", " | ".join(f.suggested_checks))
    if f.suggested_fixes:
        _detail(console, "Fixes", "; ".join(f.suggested_fixes))


def _detail(console: Console, label: str, value: str) -> None:
    line = Text("    ")
    line.append(f"{label}: ", style="dim")
    line.append(value)
    console.print(line)
