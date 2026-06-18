# Installation

Redis Doctor is a Python 3.11+ application. The core install has a small
dependency set (Typer, redis-py, Rich, Pydantic, PyYAML). Optional features live
behind extras.

## pip / pipx

```bash
pipx install redis-doctor      # isolated, on your PATH (recommended)
pip install redis-doctor       # into the current environment
```

The console entry point is `redis-doctor` (also runnable as `python -m redis_doctor`).

## Extras

| Extra | Adds | Pulls in |
|---|---|---|
| `tui` | the interactive [terminal UI](guides/tui.md) | Textual |
| `gui` | the [web dashboard](guides/gui.md), scheduling, PDF export | FastAPI, uvicorn, APScheduler, WeasyPrint |

```bash
pip install 'redis-doctor[tui]'
pip install 'redis-doctor[gui]'
pip install 'redis-doctor[tui,gui]'
```

If you launch `tui` or `serve` without the matching extra, the tool exits with a
clear message telling you which extra to install (exit code `4`).

### WeasyPrint system libraries (PDF export)

PDF export renders HTML with WeasyPrint, which needs native libraries (Pango,
Cairo, GDK-PixBuf). On Debian/Ubuntu:

```bash
apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libcairo2
```

Markdown and JSON export have no such requirement.

## Docker

A multi-stage `Dockerfile` ships with the project:

```bash
docker build -t redis-doctor .
docker run --rm redis-doctor analyze redis://host.docker.internal:6379
```

The image runs as an unprivileged user and uses `redis-doctor` as its entry point.

## Standalone binary

Build a single self-contained executable with PyInstaller:

```bash
pip install pyinstaller
pyinstaller redis-doctor.spec     # produces dist/redis-doctor
./dist/redis-doctor analyze redis://localhost:6379
```

The spec bundles the default rule pack and excludes the heavy optional GUI/TUI
dependencies to keep the binary small.

## From source (development)

```bash
git clone <repo> && cd redis-doctor
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,tui,gui]"
pytest -q
```

See [Testing](developer/testing.md) for how the test suite is structured and the
coverage gate.

## Verifying the install

```bash
redis-doctor version
redis-doctor --help
```
