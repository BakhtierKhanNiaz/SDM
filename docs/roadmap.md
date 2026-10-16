# Roadmap

Milestones run in order. A milestone is **Done** only when its acceptance criteria have been met
and its tests have actually run and passed.

| Milestone | Goal | Status |
|---|---|---|
| M0 | Inspect the environment, repository and dependencies | Done (2026-10-17) |
| M1 | Project structure, configuration, documentation, initial desktop window | Done (2026-10-17) |
| M2 | Reliable single-connection HTTP downloader | Implemented and tested; real-world demo and IDM comparison pending |
| M3 | Progress, cancellation, history and persistent state | Next |
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

## M2: Single-connection downloader

Done on branch `m2/single-connection-downloader`:

- HTTP library chosen by measurement: aiohttp (ADR-0006, `scripts/bench_http_clients/`).
- Spec FEAT-001; network policy (ADR-0007); naming and no-overwrite policy (ADR-0008).
- `sdm-get` command line; local mock server; unit, integration and security tests.

Remaining before M2 is **Done**:

- [ ] One real-world download from a URL the owner chooses (manual demonstration).
- [ ] IDM comparison for the scenarios in
  [behavior-observations.md](research/behavior-observations.md). Features become *Verified*
  in the parity matrix only after this.
