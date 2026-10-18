# SDM — Smart Download Manager

A personal-use download manager for Windows. It's modelled on the observable behavior of
Internet Download Manager (IDM) and written from scratch (clean-room).

> **Status: M2, single-connection downloader.** `sdm-get` downloads one file from the command
> line. The window is still empty (downloads appear in it from M3). See
> [docs/roadmap.md](docs/roadmap.md).

## Requirements

- Windows 10 or 11
- Python 3.12 or newer (developed on 3.14)
- [uv](https://docs.astral.sh/uv/): creates the virtual environment and installs dependencies
- Git

## Set up

```powershell
cd D:\Projects\SDM
uv sync
```

`uv sync` creates `.venv\` and installs the exact package versions recorded in `uv.lock`.
You don't need to activate the virtual environment: prefix commands with `uv run`.

## Run

```powershell
uv run python app.py                                   # the window (empty for now)
uv run sdm-get https://example.com/file.zip            # download into your Downloads folder
uv run sdm-get URL --dest D:\Downloads                 # choose the folder
uv run sdm-get URL --allow-local-network               # allow e.g. a NAS at 192.168.x.x
```

`sdm-get` never overwrites a file: if `file.zip` exists, it saves `file (1).zip`. If the
server doesn't say how big the file is, `sdm-get` still saves it but warns that it can't
confirm the whole file arrived. For safety, it refuses addresses on this computer and, unless
you pass `--allow-local-network`, on your local network.

## Test and lint

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The tests draw windows off-screen, so nothing pops up while they run.

## Project layout

| Path | Purpose |
|---|---|
| `app.py` | Launcher for running from source |
| `src/sdm/core/` | Shared building blocks; imports no other SDM package |
| `src/sdm/engine/` | HTTP download engine (M2+); never imports Qt |
| `src/sdm/storage/` | SQLite persistence (M3+) |
| `src/sdm/scheduler/` | Queues and scheduling (M6+) |
| `src/sdm/bridge/` | Browser native messaging host (M7+) |
| `src/sdm/ui/` | PySide6 desktop interface |
| `src/sdm/cli.py` | The `sdm-get` command |
| `tests/` | `unit/`, `integration/` (local mock server), `security/` |
| `scripts/` | Reproducible evaluations, e.g. the HTTP library benchmark |
| `docs/` | Research, requirements, architecture, testing, decisions |

## Documentation

- [Project brief](docs/project-brief.md): the full mission and rules
- [Roadmap](docs/roadmap.md) and [feature-parity matrix](docs/feature-parity-matrix.md)
- [System architecture](docs/architecture/system-architecture.md) and
  [security model](docs/architecture/security-model.md)
- [Architecture decision records](docs/decisions/architecture-decision-records.md)
- [Test strategy](docs/testing/test-strategy.md)
- [Changelog](CHANGELOG.md)
