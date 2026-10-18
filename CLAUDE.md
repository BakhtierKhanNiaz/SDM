# SDM — guide for Claude Code

SDM (Smart Download Manager) is a personal-use, zero-budget alternative to Internet Download
Manager (IDM) for Windows, built by behavioral reverse engineering and a clean-room
implementation. **Read [docs/project-brief.md](docs/project-brief.md) before starting a
milestone**; it is the full mission, rules and milestone list.

## Working with the user

- The user is learning software engineering. Mentor them: for each milestone explain what and
  why, which files change, how it works, how to run and test it, what success looks like, and
  how to diagnose failures. Beginner-friendly language, professional standards.
- Follow the milestones in order ([docs/roadmap.md](docs/roadmap.md)). Small, verifiable changes.
- Ask before architecture changes, destructive or security-sensitive actions, and anything
  outside this folder. Do safe work yourself instead of asking the user to do it.
- Never claim something works until its implementation and tests have actually run and passed.
  Report failures with the real output.

## Environment facts (verified in M0, 2026-10-17)

- Windows 10 Pro, i3-8100, 8 GB RAM, no GPU, $0 budget: free/open-source tools only; no paid
  services, cloud infrastructure or AI APIs without approval.
- Develop on Python 3.14; minimum supported is 3.12 (`requires-python = ">=3.12"`). Don't use
  features newer than 3.12; ruff's `UP` rules target py312.
- uv manages `.venv` and dependencies. Use `uv add` / `uv run`, not pip or venv activation
  (PowerShell script execution is restricted for the user, so `Activate.ps1` fails).
- Git is at `C:\Program Files\Git\cmd\git.exe` (on PATH for new shells).
- Windows Defender **Controlled Folder Access is on**: Documents, Desktop, Pictures, Videos and
  Music block writes from unrecognized apps. That is why the project lives on `D:\`. A blocked
  write reaches Python as `FileNotFoundError` even though the folder exists; SDM translates it.
- This shell's PATH may predate the Git install: if `git` isn't found, use the full path above.
- Windows long paths are disabled: full paths are limited to about 260 characters.
- IDM 6.42 build 22 and Free Download Manager are installed and registered as Chrome native
  messaging hosts. Test SDM's extension in a separate Chrome profile; give SDM's host a unique name.

## Commands

```powershell
uv sync                     # create/update .venv from uv.lock
uv run python app.py        # start the app
uv run sdm-get URL          # download one file (--dest, --allow-local-network, -v)
uv run pytest               # all tests (Qt off-screen, local mock HTTP server)
uv run ruff check .         # lint
uv run ruff format .        # format
uv add <pkg>                # runtime dependency; `uv add --dev <pkg>` for dev tools
```

## Layout and boundaries

- `app.py`: launcher. `src/sdm/app.py`: creates the QApplication.
- `src/sdm/core`: shared types, settings, paths, logging; imports no other SDM package.
- `src/sdm/engine`: asyncio + aiohttp download engine (ADR-0006); **never imports Qt**.
  `policy.py` is the SSRF defense (ADR-0007): keep every new request path going through it.
- `src/sdm/storage`: SQLite. `src/sdm/scheduler`: queues and scheduling.
- `src/sdm/bridge`: native messaging host; all messages are untrusted.
- `src/sdm/ui`: PySide6; the only package that imports Qt widgets. `controller.py` glues the
  history, the engine and the table model on the main thread; `engine_adapter.py` turns
  engine events into Qt signals (ADR-0009). Only the main thread touches `DownloadStore`.
- `src/sdm/cli.py`: `sdm-get`. `scripts/`: reproducible evaluations.
- Never let a test open a real message box (it hangs the run); `no_blocking_dialogs` in
  `tests/conftest.py` enforces it. Long inline heredocs in the Bash tool can break on
  quotes: put multi-line edit scripts in a file under the scratchpad instead.
- `tests/unit`, `tests/integration`, `tests/security`. `MockServer` and the `fetch` fixture
  live in `tests/conftest.py` (test modules can't import each other: importlib mode).

## Non-negotiable rules

- Clean room: observe IDM only from the outside (UI, network behavior, public docs). Never
  decompile, disassemble or copy IDM code, assets or protected details. Keep observations,
  hypotheses and design choices separate, and never invent observations.
- Never bypass authentication, DRM, paywalls or access controls.
- Treat URLs, filenames, headers and browser messages as untrusted. No local HTTP server. No
  arbitrary filesystem operations through browser messages. Never run downloaded files. Never log
  secrets, cookies, tokens or private headers.
- Tests use local mock HTTP servers and synthetic files, never third-party websites. Add a
  regression test for each bug when practical.
- Before adding a dependency, check its license and Python 3.12–3.14 Windows support, and record
  the choice in [the ADRs](docs/decisions/architecture-decision-records.md).
- Git: focused commits at stable points, one branch per milestone. No force-push, reset or
  destructive cleanup without approval.

## Keep these docs current

At the end of each milestone, update the [roadmap](docs/roadmap.md),
[feature-parity matrix](docs/feature-parity-matrix.md) and [CHANGELOG](CHANGELOG.md), plus any
architecture, security, data-model, testing, research or requirements doc that the change affects.
