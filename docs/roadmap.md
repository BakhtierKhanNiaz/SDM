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
| M5 | Parallel segmented downloads | Done (2026-10-19) |
| M6 | Queue management and scheduling | Done (2026-10-19) |
| M7 | Chrome extension and native messaging bridge | Done (2026-10-19) |
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

## M5: Parallel segmented downloads (done)

Done on branch `m5/segmented-downloads`:

- M5a (`b5590ea`): split downloads over up to 8 connections, exact-`206` validation, fallback
  to one connection, per-part retries, a sparse pre-sized partial file, an off-thread `fsync`
  before saving the parts map, history schema version 3, and resume part by part (ADR-0012).
- M5b: dynamic splitting (free connections take over half of the biggest part), the
  connection count in the window ("Downloading · 8 connections"), spec FEAT-004.

Checked on 2026-10-19: 343 tests pass (three full runs), ruff is clean, and
`uv run python app.py` opens and closes cleanly; it upgraded the real history to schema 3 with
both entries kept. With the defaults against a local server limited to 0.4 MB/s per
connection, the window showed "Downloading · 8 connections" at 3.0 MB/s.

Found and fixed while testing:

- `fsync` on the event loop thread stalled every connection on a busy disk (a speed test that
  only failed in full runs); it now runs on a worker thread.
- A part's reply was checked against its end *after* a dynamic split had shrunk it, so a
  correct reply looked wrong and the file restarted.
- The connection count briefly counted a finished part twice.

Acceptance criteria, all met on 2026-10-19:

- [x] One real-world segmented download (approved by the owner): python.org's
  `python-3.14.7-embed-amd64.zip` (12,673,227 bytes) through the window code with the real
  history, default policy and default settings. The window showed up to 8 connections
  (counts seen: 2, 3, 5, 7, 8); the engine logged no fallback, so every part came back as an
  exact `206`. Done in 3.8 s as `python-3.14.7-embed-amd64 (3).zip`; the SHA-256 matched
  python.org's published value; the three earlier copies were untouched; no `.sdmpart` left;
  the history entry is completed and verified, with its parts map cleared.
- [ ] Optional: IDM comparison against a resumable server.

## M6: Queue management and scheduling (done)

Done on branch `m6/queue-scheduling`:

- M6a (`9217188`): the queue planner (order, limit 1-8, schedule, Start now, automatic retries
  after about 1, 5 and 15 minutes), categories, history schema version 4 with a settings
  table; the controller's `pump()` is the only place that starts downloads (ADR-0013).
- M6b: a Queue menu (Start now, Move to top/up/down/bottom), the Scheduler dialog (limit,
  times and days, category subfolders), "Start the download now" in Add URL, and a Category
  column with a filter. Spec FEAT-005.

Checked on 2026-10-19: 395 tests pass (three full runs), ruff is clean, and
`uv run python app.py` opens and closes cleanly; it upgraded the real history to schema 4.
That launch check showed existing entries labelled "General": upgrades now label existing
entries from their file names (the owner's history had already been upgraded, so its three
entries keep "General"). A screenshot showed the limit of 2 holding with three waiting.

Acceptance criteria, all met on 2026-10-19:

- [x] One real-world scheduled download (approved by the owner): python.org's
  `python-3.14.7-embed-amd64.zip` through the window code with the real history and policy,
  and a schedule window of 03:10-03:40. Added at 03:08:31, it waited as Queued; the app's own
  30-second timer (no manual `pump()`) started it at 03:10:01, 1.7 s after the window opened.
  Saved as `python-3.14.7-embed-amd64 (4).zip`, category Compressed; the SHA-256 matched
  python.org's published value; the earlier four copies were untouched. The owner's queue
  settings were saved before the demo and restored afterwards (checked).
- [ ] Optional: observe IDM's queue and scheduler screens (checklist).

## M7: Chrome extension and native messaging bridge (done)

Done on branch `m7/browser-bridge` (ADR-0014, spec FEAT-006):

- `sdm.bridge.protocol`: framing (4-byte length + JSON, 64 KiB cap) and the strict request
  schema. `sdm.bridge.pipe`: the per-user key, the authenticated named pipe, the listener
  and client. `sdm.bridge.host`: the host Chrome starts; it starts SDM if needed.
  `sdm.bridge.install`: registration for one extension ID, and its removal.
- The window: a handoff opens Add URL filled in, one at a time; the pipe makes SDM
  single-instance.
- `extension/chrome`: Manifest V3, "Download with SDM" on links; `node --test` tests.

Checked on 2026-10-19: 485 Python tests pass (90 new), 12 extension tests pass, ruff is
clean. A launch check with a throwaway `LOCALAPPDATA` used the real `sdm.exe` and host
processes: a second SDM exited quietly in 1.2 s; the host handed a link to the running SDM in
0.2 s; with SDM closed, the host started it and got `{"ok": true}` in 1.5 s.

Acceptance, all met on 2026-10-19:

- [x] Register the host (approved by the owner, 2026-10-19): one HKCU value pointing at
  `%LOCALAPPDATA%\SDM\bridge\com.sdm.bridge.json`, allowed origin limited to the owner's
  extension ID. The launcher, run through `cmd.exe` as Chrome does, refused a message with an
  extra field (`bad_request`) and wrote nothing else to stdout.
- [x] Chrome finds and runs the registered host (2026-10-19). The owner's first try said
  "host not found": that Chrome had been running since before the registration. A fresh
  throwaway Chrome (same program, same Windows account) found it at once: an invalid link got
  `bad_request`, and a valid one started SDM (throwaway data) and got `{"ok": true}`.
  `scripts/chrome_bridge_check/check.mjs` repeats the first check; the install script and the
  extension's tooltip now say to restart Chrome completely.
- [x] Owner's Chrome check (in the owner's Default profile rather than a separate one; IDM's
  extension is also installed there, which didn't interfere with the right-click item):
  - With SDM closed, a right-click handoff started SDM (`sdm.exe --from-browser`, 5:42:05 PM)
    and opened "Add URL from the browser" filled in. That link was a web page, so the owner
    pressed Cancel: no history entry was added.
  - With SDM running, a handoff of python.org's `python-3.15.0-amd64.exe` was confirmed and
    completed: 45,383,680 bytes, the size the server announced, category Programs, in
    about 9 s. The file was not opened or run.
  - The first two tries said "host not found" while the extension and registration were
    correct; after Chrome was fully closed and reopened it worked. The exact cause of those
    failures wasn't captured (Chrome's log was only switched on for the try that worked).
