"""Typer CLI: all subcommands."""

from __future__ import annotations

import os

import typer
from rich.console import Console

from . import __version__
from .config import ENV_PASSWORD, ENV_USERNAME, load_config
from .connection import connect, parse_target
from .errors import ConfigError, ExitCode, RedisDoctorError
from .logging import configure as configure_logging
from .models.report import Report
from .output import json_out, terminal
from .pipeline import run_pipeline

app = typer.Typer(
    name="redis-doctor",
    help="Diagnose the production health of a Redis deployment.",
    no_args_is_help=True,
    add_completion=True,
)

console = Console()
err_console = Console(stderr=True)


# --- shared option groups -------------------------------------------------


def _resolve_target(
    url: str | None,
    host: str | None,
    port: int | None,
    db: int | None,
    username: str | None,
    password: str | None,
    tls: bool,
    tls_ca_cert: str | None,
    tls_cert: str | None,
    tls_key: str | None,
    socket_timeout: float,
    connect_timeout: float,
):
    username = username or os.environ.get(ENV_USERNAME)
    password = password or os.environ.get(ENV_PASSWORD)
    return parse_target(
        url,
        host=host,
        port=port,
        db=db,
        username=username,
        password=password,
        tls=tls,
        tls_ca_cert=tls_ca_cert,
        tls_cert=tls_cert,
        tls_key=tls_key,
        socket_timeout=socket_timeout,
        connect_timeout=connect_timeout,
    )


def _run(fn) -> None:
    """Execute a command body, mapping RedisDoctorError to its exit code."""
    configure_logging()
    try:
        code = fn()
    except RedisDoctorError as e:
        err_console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(e.exit_code) from e
    except typer.Exit:
        raise
    except Exception as e:  # noqa: BLE001 — last-resort guard -> exit 5
        err_console.print(f"[red]internal error:[/red] {e}")
        raise typer.Exit(ExitCode.INTERNAL_ERROR) from e
    raise typer.Exit(code or ExitCode.SUCCESS)


# --- output + exit-code helpers -------------------------------------------


def _split_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


def _scan_overrides(
    sample_size: int | None,
    scan_count: int | None,
    max_scan_seconds: float | None,
    prefix_depth: int | None,
    prefix_separators: str | None,
) -> dict:
    mapping = {
        "sample_size": sample_size,
        "count": scan_count,
        "max_seconds": max_scan_seconds,
        "prefix_depth": prefix_depth,
        "prefix_separators": prefix_separators,
    }
    return {k: v for k, v in mapping.items() if v is not None}


def compute_exit_code(report: Report, fail_on: str, no_fail: bool) -> int:
    """Map findings to the exit-code contract (Section 7.4)."""
    if no_fail or fail_on == "none":
        return ExitCode.SUCCESS
    if fail_on not in ("warning", "critical"):
        raise ConfigError(f"invalid --fail-on value: {fail_on!r}")
    if report.summary.critical > 0:
        return ExitCode.FINDINGS_CRITICAL
    if fail_on == "warning" and report.summary.warning > 0:
        return ExitCode.FINDINGS_WARNING
    return ExitCode.SUCCESS


def emit_report(report: Report, fmt: str, output: str | None) -> None:
    if fmt == "json":
        text = json_out.render_json(report)
    elif fmt == "markdown":
        from .output import markdown

        text = markdown.render_markdown(report)
    elif fmt == "terminal":
        if output:
            with open(output, "w") as fh:
                terminal.render(report, Console(file=fh, force_terminal=False))
        else:
            terminal.render(report, console)
        return
    else:
        raise ConfigError(f"invalid --format value: {fmt!r}")

    if output:
        with open(output, "w") as fh:
            fh.write(text)
    else:
        console.print(text, soft_wrap=True, markup=False, highlight=False)


def run_and_emit(
    *,
    conn: dict,
    config: str | None,
    fmt: str | None,
    output: str | None,
    fail_on: str | None,
    no_fail: bool,
    only: list[str] | None = None,
    skip: list[str] | None = None,
    options: dict | None = None,
    scan_overrides: dict | None = None,
    disable_dependencies: bool = False,
) -> int:
    """Shared body for analysis subcommands: connect, run pipeline, emit, exit code."""
    cfg = load_config(config)
    if scan_overrides:
        cfg.scan = cfg.scan.model_copy(update=scan_overrides)
    resolved_fmt = fmt or cfg.output.format
    resolved_fail_on = fail_on or cfg.output.fail_on
    target = _resolve_target(**conn)
    safe = connect(target)
    try:
        report = run_pipeline(
            safe,
            cfg,
            options=options or {},
            only=only,
            skip=skip,
            disable_dependencies=disable_dependencies,
        )
    finally:
        safe.close()

    if cfg.history.enabled:
        from .history.store import HistoryStore

        HistoryStore(cfg.history.path).save(report)
    if cfg.notify.slack_webhook_url or cfg.notify.email:
        from .notify import notify as send_notify

        send_notify(
            report, cfg.notify, resolved_fail_on if resolved_fail_on != "none" else "warning"
        )

    emit_report(report, resolved_fmt, output)
    return compute_exit_code(report, resolved_fail_on, no_fail)


# --- analyze --------------------------------------------------------------


@app.command()
def analyze(
    url: str | None = typer.Argument(None, help="redis:// connection URL"),
    host: str | None = typer.Option(None),
    port: int | None = typer.Option(None),
    db: int | None = typer.Option(None),
    username: str | None = typer.Option(None),
    password: str | None = typer.Option(None),
    tls: bool = typer.Option(False, "--tls"),
    tls_ca_cert: str | None = typer.Option(None, "--tls-ca-cert"),
    tls_cert: str | None = typer.Option(None, "--tls-cert"),
    tls_key: str | None = typer.Option(None, "--tls-key"),
    socket_timeout: float = typer.Option(5.0, "--socket-timeout"),
    connect_timeout: float = typer.Option(5.0, "--connect-timeout"),
    config: str | None = typer.Option(None, "--config"),
    fmt: str | None = typer.Option(None, "--format"),
    output: str | None = typer.Option(None, "--output"),
    fail_on: str | None = typer.Option(None, "--fail-on"),
    no_fail: bool = typer.Option(False, "--no-fail"),
    only: str | None = typer.Option(None, "--only", help="run only these modules"),
    skip: str | None = typer.Option(None, "--skip", help="skip these modules"),
    fleet: str | None = typer.Option(None, "--fleet", help="fleet YAML of targets"),
) -> None:
    """Full diagnostic run (the primary command)."""

    conn = dict(
        url=url,
        host=host,
        port=port,
        db=db,
        username=username,
        password=password,
        tls=tls,
        tls_ca_cert=tls_ca_cert,
        tls_cert=tls_cert,
        tls_key=tls_key,
        socket_timeout=socket_timeout,
        connect_timeout=connect_timeout,
    )

    def body() -> int:
        if fleet:
            return _run_fleet(fleet, config, output)
        return run_and_emit(
            conn=conn,
            config=config,
            fmt=fmt,
            output=output,
            fail_on=fail_on,
            no_fail=no_fail,
            only=_split_csv(only),
            skip=_split_csv(skip),
        )

    _run(body)


def _run_fleet(fleet_path: str, config: str | None, output: str | None) -> int:
    """Run all targets in a fleet file sequentially; write one combined JSON."""
    import json

    import yaml

    cfg = load_config(config)
    try:
        spec = yaml.safe_load(open(fleet_path).read()) or {}
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(f"could not read fleet file {fleet_path}: {e}") from e
    targets = spec.get("targets", [])
    instances = []
    for entry in targets:
        url = entry.get("url") if isinstance(entry, dict) else entry
        name = entry.get("name", url) if isinstance(entry, dict) else url
        try:
            target = parse_target(url)
            safe = connect(target)
            try:
                report = run_pipeline(safe, cfg)
            finally:
                safe.close()
            instances.append(
                {
                    "name": name,
                    "target": target.redacted_url(),
                    "score": report.health_score,
                    "report": report.model_dump(mode="json"),
                }
            )
        except RedisDoctorError as e:
            instances.append({"name": name, "target": url, "error": str(e)})
    combined = json.dumps({"instances": instances}, indent=2, default=str)
    if output:
        with open(output, "w") as fh:
            fh.write(combined)
    else:
        console.print(combined, markup=False, highlight=False)
    return ExitCode.SUCCESS


@app.command(name="analyze-sentinel")
def analyze_sentinel(
    sentinel_node: list[str] = typer.Option(
        ..., "--sentinel-node", help="Sentinel host:port (repeatable)"
    ),
    master_name: str = typer.Option(..., "--master-name"),
    password: str | None = typer.Option(None, "--password"),
    sentinel_password: str | None = typer.Option(None, "--sentinel-password"),
    config: str | None = typer.Option(None, "--config"),
    fmt: str | None = typer.Option(None, "--format"),
    output: str | None = typer.Option(None, "--output"),
    fail_on: str | None = typer.Option(None, "--fail-on"),
    no_fail: bool = typer.Option(False, "--no-fail"),
) -> None:
    """Sentinel topology diagnostic."""
    from .analyzers.sentinel_rules import analyze_sentinel as run_sentinel
    from .collectors.sentinel import collect_sentinel
    from .pipeline import build_report

    def body() -> int:
        cfg = load_config(config)
        topo = collect_sentinel(sentinel_node, master_name, sentinel_password)
        findings = run_sentinel(topo, cfg)
        stats = {
            "sentinel": {
                "master_name": topo.master_name,
                "quorum": topo.quorum,
                "reachable_sentinels": topo.reachable_sentinels,
                "configured_sentinels": topo.configured_sentinels,
                "master_addrs": sorted(topo.master_addrs),
                "replicas": [
                    {"addr": r.addr, "lag_seconds": r.lag_seconds, "reachable": r.reachable}
                    for r in topo.replicas
                ],
                "errors": topo.errors,
            }
        }
        report = build_report(f"sentinel://{master_name}", findings, config=cfg, stats=stats)
        emit_report(report, fmt or cfg.output.format, output)
        return compute_exit_code(report, fail_on or cfg.output.fail_on, no_fail)

    _run(body)


@app.command(name="analyze-cluster")
def analyze_cluster(
    url: str | None = typer.Argument(None),
    host: str | None = typer.Option(None),
    port: int | None = typer.Option(None),
    password: str | None = typer.Option(None),
    tls: bool = typer.Option(False, "--tls"),
    socket_timeout: float = typer.Option(5.0, "--socket-timeout"),
    connect_timeout: float = typer.Option(5.0, "--connect-timeout"),
    config: str | None = typer.Option(None, "--config"),
    fmt: str | None = typer.Option(None, "--format"),
    output: str | None = typer.Option(None, "--output"),
    fail_on: str | None = typer.Option(None, "--fail-on"),
    no_fail: bool = typer.Option(False, "--no-fail"),
) -> None:
    """Cluster diagnostic."""
    from .analyzers.cluster_rules import analyze_cluster as run_cluster
    from .collectors.cluster import collect_cluster
    from .pipeline import build_report

    def body() -> int:
        cfg = load_config(config)
        target = _resolve_target(
            url,
            host,
            port,
            None,
            None,
            password,
            tls,
            None,
            None,
            None,
            socket_timeout,
            connect_timeout,
        )
        safe = connect(target)
        try:
            data = collect_cluster(safe, password)
        finally:
            safe.close()
        if not data.enabled:
            console.print("This instance is not running in cluster mode.")
            return ExitCode.SUCCESS
        findings = run_cluster(data)
        stats = {
            "cluster": {
                "state": data.state,
                "slots_assigned": data.slots_assigned,
                "uncovered_slots": data.uncovered_slots,
                "known_nodes": data.known_nodes,
                "size": data.size,
                "nodes": [
                    {
                        "addr": n.addr,
                        "role": n.role,
                        "slots": n.slots,
                        "keys": n.keys,
                        "used_memory": n.used_memory,
                        "clients": n.clients,
                        "failed": n.failed,
                        "reachable": n.reachable,
                    }
                    for n in data.nodes
                ],
            }
        }
        report = build_report(target.redacted_url(), findings, config=cfg, stats=stats)
        emit_report(report, fmt or cfg.output.format, output)
        return compute_exit_code(report, fail_on or cfg.output.fail_on, no_fail)

    _run(body)


@app.command(name="scan-keys")
def scan_keys(
    url: str | None = typer.Argument(None),
    host: str | None = typer.Option(None),
    port: int | None = typer.Option(None),
    db: int | None = typer.Option(None),
    username: str | None = typer.Option(None),
    password: str | None = typer.Option(None),
    tls: bool = typer.Option(False, "--tls"),
    tls_ca_cert: str | None = typer.Option(None, "--tls-ca-cert"),
    tls_cert: str | None = typer.Option(None, "--tls-cert"),
    tls_key: str | None = typer.Option(None, "--tls-key"),
    socket_timeout: float = typer.Option(5.0, "--socket-timeout"),
    connect_timeout: float = typer.Option(5.0, "--connect-timeout"),
    config: str | None = typer.Option(None, "--config"),
    fmt: str | None = typer.Option(None, "--format"),
    output: str | None = typer.Option(None, "--output"),
    sample_size: int | None = typer.Option(None, "--sample-size"),
    scan_count: int | None = typer.Option(None, "--scan-count"),
    max_scan_seconds: float | None = typer.Option(None, "--max-scan-seconds"),
    prefix_depth: int | None = typer.Option(None, "--prefix-depth"),
    prefix_separators: str | None = typer.Option(None, "--prefix-separators"),
) -> None:
    """Keyspace + prefix report only."""
    conn = dict(
        url=url,
        host=host,
        port=port,
        db=db,
        username=username,
        password=password,
        tls=tls,
        tls_ca_cert=tls_ca_cert,
        tls_cert=tls_cert,
        tls_key=tls_key,
        socket_timeout=socket_timeout,
        connect_timeout=connect_timeout,
    )
    scan_overrides = _scan_overrides(
        sample_size, scan_count, max_scan_seconds, prefix_depth, prefix_separators
    )

    def body() -> int:
        return run_and_emit(
            conn=conn,
            config=config,
            fmt=fmt,
            output=output,
            fail_on="none",
            no_fail=True,
            only=["server", "keyspace"],
            scan_overrides=scan_overrides,
        )

    _run(body)


@app.command(name="inspect-stream")
def inspect_stream(
    url: str | None = typer.Argument(None),
    stream: str = typer.Argument(..., help="stream key name"),
    host: str | None = typer.Option(None),
    port: int | None = typer.Option(None),
    db: int | None = typer.Option(None),
    username: str | None = typer.Option(None),
    password: str | None = typer.Option(None),
    tls: bool = typer.Option(False, "--tls"),
    socket_timeout: float = typer.Option(5.0, "--socket-timeout"),
    connect_timeout: float = typer.Option(5.0, "--connect-timeout"),
    config: str | None = typer.Option(None, "--config"),
    fmt: str | None = typer.Option(None, "--format"),
    output: str | None = typer.Option(None, "--output"),
) -> None:
    """Deep single-stream diagnostic."""
    conn = dict(
        url=url,
        host=host,
        port=port,
        db=db,
        username=username,
        password=password,
        tls=tls,
        tls_ca_cert=None,
        tls_cert=None,
        tls_key=None,
        socket_timeout=socket_timeout,
        connect_timeout=connect_timeout,
    )

    def body() -> int:
        return run_and_emit(
            conn=conn,
            config=config,
            fmt=fmt,
            output=output,
            fail_on="none",
            no_fail=True,
            only=["server", "streams"],
            options={"stream_names": [stream]},
            disable_dependencies=True,
        )

    _run(body)


@app.command(name="inspect-clients")
def inspect_clients(
    url: str | None = typer.Argument(None),
    host: str | None = typer.Option(None),
    port: int | None = typer.Option(None),
    db: int | None = typer.Option(None),
    username: str | None = typer.Option(None),
    password: str | None = typer.Option(None),
    tls: bool = typer.Option(False, "--tls"),
    socket_timeout: float = typer.Option(5.0, "--socket-timeout"),
    connect_timeout: float = typer.Option(5.0, "--connect-timeout"),
    config: str | None = typer.Option(None, "--config"),
    fmt: str | None = typer.Option(None, "--format"),
    output: str | None = typer.Option(None, "--output"),
) -> None:
    """Client analysis only."""
    conn = dict(
        url=url,
        host=host,
        port=port,
        db=db,
        username=username,
        password=password,
        tls=tls,
        tls_ca_cert=None,
        tls_cert=None,
        tls_key=None,
        socket_timeout=socket_timeout,
        connect_timeout=connect_timeout,
    )

    def body() -> int:
        return run_and_emit(
            conn=conn,
            config=config,
            fmt=fmt,
            output=output,
            fail_on="none",
            no_fail=True,
            only=["server", "clients"],
        )

    _run(body)


@app.command(name="config-check")
def config_check(
    url: str | None = typer.Argument(None),
    host: str | None = typer.Option(None),
    port: int | None = typer.Option(None),
    db: int | None = typer.Option(None),
    username: str | None = typer.Option(None),
    password: str | None = typer.Option(None),
    tls: bool = typer.Option(False, "--tls"),
    tls_ca_cert: str | None = typer.Option(None, "--tls-ca-cert"),
    tls_cert: str | None = typer.Option(None, "--tls-cert"),
    tls_key: str | None = typer.Option(None, "--tls-key"),
    socket_timeout: float = typer.Option(5.0, "--socket-timeout"),
    connect_timeout: float = typer.Option(5.0, "--connect-timeout"),
    config: str | None = typer.Option(None, "--config"),
    fmt: str | None = typer.Option(None, "--format"),
    output: str | None = typer.Option(None, "--output"),
    fail_on: str | None = typer.Option(None, "--fail-on"),
    no_fail: bool = typer.Option(False, "--no-fail"),
) -> None:
    """Config + persistence + replication risk only.

    The server module also runs so the summary header is populated.
    """
    conn = dict(
        url=url,
        host=host,
        port=port,
        db=db,
        username=username,
        password=password,
        tls=tls,
        tls_ca_cert=tls_ca_cert,
        tls_cert=tls_cert,
        tls_key=tls_key,
        socket_timeout=socket_timeout,
        connect_timeout=connect_timeout,
    )

    def body() -> int:
        return run_and_emit(
            conn=conn,
            config=config,
            fmt=fmt,
            output=output,
            fail_on=fail_on,
            no_fail=no_fail,
            only=["server", "config", "persistence", "replication"],
        )

    _run(body)


@app.command()
def report(
    input_json: str = typer.Argument(..., help="path to a saved JSON report"),
    fmt: str = typer.Option("terminal", "--format"),
    output: str | None = typer.Option(None, "--output"),
) -> None:
    """Re-render a saved JSON report in another format."""

    def body() -> int:
        import json

        try:
            with open(input_json) as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as e:
            raise ConfigError(f"could not read report {input_json}: {e}") from e
        try:
            rep = Report.model_validate(data)
        except Exception as e:
            raise ConfigError(f"invalid report schema: {e}") from e
        emit_report(rep, fmt, output)
        return ExitCode.SUCCESS

    _run(body)


@app.command()
def diff(
    before: str = typer.Argument(..., help="earlier report JSON"),
    after: str = typer.Argument(..., help="later report JSON"),
    fmt: str = typer.Option("terminal", "--format"),
    output: str | None = typer.Option(None, "--output"),
) -> None:
    """Diff two saved JSON reports."""
    from .history.diff import diff_reports, render_diff_text

    def body() -> int:
        try:
            before_rep = Report.model_validate_json(open(before).read())
            after_rep = Report.model_validate_json(open(after).read())
        except (OSError, ValueError) as e:
            raise ConfigError(f"could not load reports: {e}") from e
        d = diff_reports(before_rep, after_rep)
        text = d.model_dump_json(indent=2) if fmt == "json" else render_diff_text(d)
        if output:
            with open(output, "w") as fh:
                fh.write(text)
        else:
            console.print(text, markup=False, highlight=False)
        return ExitCode.SUCCESS

    _run(body)


@app.command()
def tui(
    url: str | None = typer.Argument(None),
    host: str | None = typer.Option(None),
    port: int | None = typer.Option(None),
    db: int | None = typer.Option(None),
    username: str | None = typer.Option(None),
    password: str | None = typer.Option(None),
    tls: bool = typer.Option(False, "--tls"),
    tls_ca_cert: str | None = typer.Option(None, "--tls-ca-cert"),
    tls_cert: str | None = typer.Option(None, "--tls-cert"),
    tls_key: str | None = typer.Option(None, "--tls-key"),
    socket_timeout: float = typer.Option(5.0, "--socket-timeout"),
    connect_timeout: float = typer.Option(5.0, "--connect-timeout"),
    config: str | None = typer.Option(None, "--config"),
) -> None:
    """Interactive terminal UI."""
    conn = dict(
        url=url,
        host=host,
        port=port,
        db=db,
        username=username,
        password=password,
        tls=tls,
        tls_ca_cert=tls_ca_cert,
        tls_cert=tls_cert,
        tls_key=tls_key,
        socket_timeout=socket_timeout,
        connect_timeout=connect_timeout,
    )

    def body() -> int:
        try:
            from .tui.app import RedisDoctorTUI
        except ImportError as e:
            raise ConfigError(
                "the TUI requires the 'textual' extra: pip install 'redis-doctor[tui]'"
            ) from e

        cfg = load_config(config)
        target = _resolve_target(**conn)

        def run_analysis() -> Report:
            safe = connect(target)
            try:
                return run_pipeline(safe, cfg)
            finally:
                safe.close()

        RedisDoctorTUI(run_analysis, target=target.redacted_url()).run()
        return ExitCode.SUCCESS

    _run(body)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port"),
    config: str | None = typer.Option(None, "--config"),
    fleet: str | None = typer.Option(None, "--fleet", help="fleet YAML for the Fleet view"),
) -> None:
    """Launch the local web GUI + JSON API."""

    def body() -> int:
        try:
            from .gui.server import load_fleet
            from .gui.server import serve as run_server
        except ImportError as e:
            raise ConfigError(
                "the GUI requires the 'gui' extra: pip install 'redis-doctor[gui]'"
            ) from e
        cfg = load_config(config)
        fleet_targets = load_fleet(fleet) if fleet else None
        console.print(f"redis-doctor serving on http://{host}:{port}")
        run_server(host=host, port=port, config=cfg, fleet=fleet_targets)
        return ExitCode.SUCCESS

    _run(body)


@app.command()
def version() -> None:
    """Print the redis-doctor version."""
    console.print(__version__)


if __name__ == "__main__":
    app()
