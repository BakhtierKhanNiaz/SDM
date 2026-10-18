# Roadmap

Milestones run in order. A milestone is **Done** only when its acceptance criteria have been met
and its tests have actually run and passed.

| Milestone | Goal | Status |
|---|---|---|
| M0 | Inspect the environment, repository and dependencies | Done (2026-10-17) |
| M1 | Project structure, configuration, documentation, initial desktop window | Done (2026-10-17) |
| M2 | Reliable single-connection HTTP downloader | Done (2026-10-18) |
| M3 | Progress, cancellation, history and persistent state | Done (2026-10-19) |
| M4 | Pause/resume and crash recovery | Done (2026-10-19) |
| M5 | Parallel segmented downloads | In progress (M5a done) |
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

## M2: Single-connection downloader (done)

Done on branch `m2/single-connection-downloader`:

- HTTP library chosen by measurement: aiohttp (ADR-0006, `scripts/bench_http_clients/`).
- Spec FEAT-001; network policy (ADR-0007); naming and no-overwrite policy (ADR-0008).
- `sdm-get` command line; local mock server; unit, integration and security tests.

Acceptance criteria, all met on 2026-10-18: FEAT-001's tests pass (145 in total), ruff is
clean, and:

- [x] One real-world download (2026-10-17, approved by the owner):
  `uv run sdm-get https://www.python.org/ftp/python/3.14.7/python-3.14.7-embed-amd64.zip -v`
  saved 12,673,227 bytes to `Downloads` in about 3 s. The SHA-256 matched the value python.org
  publishes (`d297e5ff…a6ab1f15`), all 37 zip members passed their CRC checks, and no
  `.sdmpart` file was left behind. Nothing from the zip was run.
- [x] IDM comparison (2026-10-18): the owner ran the six scenarios in IDM by hand. They were
  checked against the scenario server's request log and the SHA-256 of every saved file, and
  recorded as OBS-001 to OBS-006 in
  [behavior-observations.md](research/behavior-observations.md). Two small fixes came out of
  it: a warning when completeness can't be confirmed (unknown size) and a "not found" message
  for 404/410. Not observed, so carried forward: IDM's live progress display for unknown sizes
  (M3) and how many times IDM retries automatically (M4).

Known issue (cosmetic, found in the real-world demo): with `-v`, log lines are printed on the
same line as `sdm-get`'s progress display, because both write to stderr and the progress line
doesn't end with a newline. The downloaded file is unaffected.

## M3: Downloads in the window, with history (done)

Done on branch `m3/window-downloads-history`:

- M3a (`6419fe8`): `DownloadManager` on its own thread (ADR-0009), the SQLite history
  (ADR-0010, data-model.md), and the speed/time-left calculator.
- M3b: the window. Add URL dialog with a "downloaded before" warning, a live table (name, size,
  percent, speed, time left, status), Cancel, Remove from list (keeps the file), a status bar
  summary, a question before quitting with downloads running, and startup notices for an
  interrupted or recovered history. Spec FEAT-002.

Checked on 2026-10-19: 234 tests pass, ruff is clean, and `uv run python app.py` opens and
closes cleanly, creating `%LOCALAPPDATA%\SDM\sdm.db` (schema 1, WAL). A screenshot with real
local downloads showed three running at once, a fourth waiting, and live numbers.

Acceptance criteria, all met on 2026-10-19:

- [x] One real-world download through the window (approved by the owner): python.org's
  `python-3.14.7-embed-amd64.zip`, through the Add URL dialog's checks and the window's
  `add_download`, with the real history and the default network policy. Saved as
  `python-3.14.7-embed-amd64 (1).zip`, because M2's copy was already there; that copy was
  untouched (same SHA-256 and timestamp). 12,673,227 bytes; the SHA-256 matched python.org's
  published value (`d297e5ff…a6ab1f15`); no `.sdmpart` left; the history entry is completed and
  verified. It took 23.9 s: the window itself measured 536 KB/s from the server. The same
  window path moves 261 MB/s over loopback, so the time was the server's and the network's.
  No "downloaded before" warning was shown, as expected: M2's copy came from `sdm-get`, which
  doesn't write to the history.
- [ ] Optional: IDM re-run R1 to compare the live progress display (makes it *Verified*).

## M4: Pause, resume and crash recovery (done)

Done on branch `m4/pause-resume`:

- M4a (`8e41d12`): resume from partial files with `Range` + `If-Range` or a 64-byte overlap
  check; only an exact `206` continues (ADR-0011). Retries continue, the `paused` state is
  added, history schema version 2, and the manager and controller can pause and resume.
- M4b: Pause, Resume (Retry for failed downloads), Resume all, and Cancel for paused entries
  in the window. A question before pausing on a server that can't resume. Quitting pauses
  ("Quit and pause them?"). Startup points to Resume / Resume all. Status tooltips say
  whether Resume continues or starts over. Spec FEAT-003.

Checked on 2026-10-19: 293 tests pass (three full runs), ruff is clean, and
`uv run python app.py` opens and closes cleanly. It upgraded the real history from schema 1
to 2 in place, keeping entry #1. A screenshot with real local downloads showed one paused at
27% beside two running.

Found and fixed while testing:

- The table had no label for `paused` (KeyError while drawing).
- The window didn't learn that a server can resume until the next state change, so Pause
  asked "Pause anyway?" for no reason.
- A race in the test server's request log (written after sending); it is now written before.
- Tests now fail at once on an unexpected message box instead of hanging.

Acceptance criteria, all met on 2026-10-19:

- [x] One real-world pause and resume across a full SDM restart (approved by the owner):
  python.org's `python-3.14.7-embed-amd64.zip`, through the window code with the real history
  and the default policy, in two separate processes. Phase 1: the Add URL dialog showed the
  "already downloaded" warning (naming the `(1)` copy); Pause at 3,932,160 of 12,673,227
  bytes (31%); partial file exactly that size; the server advertised resume, with a strong
  ETag and Last-Modified; SDM quit. Phase 2 (new process): the entry was still paused at
  3,932,160; Resume continued from there (the smallest progress shown afterwards was
  3,932,160, and the engine logged no restart); done in 3.3 s as
  `python-3.14.7-embed-amd64 (2).zip`. The SHA-256 matched python.org's published value; the
  earlier two copies were untouched; no `.sdmpart` left; history entry #2 completed and
  verified.
- [ ] Optional: IDM comparison R2 (automatic retries) and resume against a `206` server.
