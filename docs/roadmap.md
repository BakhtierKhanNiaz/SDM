# Roadmap

Milestones run in order. A milestone is **Done** only when its acceptance criteria have been met
and its tests have actually run and passed.

| Milestone | Goal | Status |
|---|---|---|
| M0 | Inspect the environment, repository and dependencies | Done (2026-10-17) |
| M1 | Project structure, configuration, documentation, initial desktop window | Done (2026-10-17) |
| M2 | Reliable single-connection HTTP downloader | Next |
| M3 | Progress, cancellation, history and persistent state | Not started |
| M4 | Pause/resume and crash recovery | Not started |
| M5 | Parallel segmented downloads | Not started |
| M6 | Queue management and scheduling | Not started |
| M7 | Chrome extension and native messaging bridge | Not started |
| M8 | Browser handoff integrated with the download engine | Not started |
| M9 | Interface, settings, notifications and usability | Not started |
| M10 | Security, performance, regression testing and Windows packaging | Not started |

## M0: Environment inspection (done)

Findings are in [research/environment-m0.md](research/environment-m0.md).

## M1: Project skeleton (done)

Acceptance criteria, all met on 2026-10-17:

- `uv run python app.py` opens the SDM window.
- `uv run pytest` passes (4 tests).
- `uv run ruff check .` and `uv run ruff format --check .` report no problems.
- The work is committed on branch `m1/project-skeleton`.

## M2: Single-connection downloader (next)

To plan at the start of M2:

- Choose the HTTP library (httpx vs aiohttp): a short evaluation recorded as an ADR.
- Write the first feature specification: download one URL to a file with status validation,
  redirects, filename detection and sanitization, unknown sizes, timeouts, a limited retry
  policy, temporary files and safe finalization, and a duplicate-filename policy.
- Set up a local mock HTTP server for tests (no third-party sites).
- Begin Stage A observations of IDM's basic download behavior for comparison.
