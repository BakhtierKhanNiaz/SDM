# Changelog

All notable changes to SDM are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow semantic versioning
while SDM is in 0.x.

## [Unreleased]

### Added

- M10a, hardening: fuzz tests for every parser of untrusted data; a log file
  (`%LOCALAPPDATA%\SDM\logs\sdm.log`, rotated, addresses redacted); a crash safety net;
  Help > Open log folder and About SDM. ADR-0017.
- M9 done: in the owner's own SDM, a python.org download held to 1 MB/s finished "Completed ·
  verified" with a matching SHA-256, a Windows notification and a working Show in folder.
- M9b, the window: Tools > Settings (default folder, remember the last folder, connections
  per download, speed limit, notifications, keep running in the tray), a SHA-256 box in Add
  URL, a tray icon with Pause all / Resume all / Quit, Windows notifications, a right-click
  menu with Show in folder, Copy address and Verify checksum, total speed in the status bar,
  and a remembered window layout. No "Open file", by design.
- M9a, the engine: one speed limit shared by every download and connection, connections per
  download, SHA-256 checks of finished files (history schema version 6), saved preferences.
  ADR-0016, spec FEAT-008; 58 new tests (628 in total).
- M8 done: in the owner's own Chrome, a captured python.org download went to SDM with the
  browser's name and page, and matched python.org's SHA-256.
- M8b, the browser: opt-in automatic capture from the extension's toolbar panel (asks
  Chrome for the `downloads` permission when turned on), a minimum size, hand-back to
  Chrome when SDM can't take a download, right-click on video and audio players, and the
  Add URL dialog showing the browser's name, size, type and page host.
- M8a, the engine: message version 2 with optional referrer, file name, size, type and
  source; the Referer sent the way browsers do on every request; the browser's name used
  when the server gives none; history schema version 5. ADR-0015, spec FEAT-007;
  85 new Python tests (570 in total) and 36 extension tests.

- M7 done: the owner's Chrome check passed (a handoff started SDM when it was closed, and a
  python.org download sent from Chrome completed). Setup guidance now says to restart
  Chrome completely after registering, and `scripts/chrome_bridge_check/check.mjs` checks
  the registration in a throwaway headless Chrome.
- M7, browser handoff: a Chrome extension (Manifest V3, `contextMenus` and
  `nativeMessaging` only) adds "Download with SDM" to links. A native messaging host
  (`com.sdm.bridge`) checks the message against a strict schema and passes it to SDM over a
  named pipe authenticated with a per-user key, starting SDM if needed. SDM opens Add URL
  filled in for the user to confirm, and now runs as a single instance.
  `python -m sdm.bridge.install` registers the host for one extension ID. ADR-0014, spec
  FEAT-006; 90 new Python tests (485 in total) and 12 extension tests.
- M6b, the window: Queue menu (Start now, Move to top/up/down/bottom), Scheduler dialog
  (downloads at once, times and days, category subfolders), "Start the download now" in
  Add URL, a Category column and a category filter. Upgrading to schema 4 labels existing
  entries by file name. Spec FEAT-005; 6 new tests (395 in total).
- M6a, the queue: a pure planner (`sdm.scheduler.queue`) decides which waiting downloads start
  and which go back to waiting: queue order, a limit of 1-8 (default 3), a schedule (start and
  stop times, days, overnight windows), Start now, and automatic retries for temporary
  failures after about 1, 5 and 15 minutes. Categories by file type, with optional IDM-style
  subfolders (off by default). History schema version 4 (queue columns, settings table).
  The controller's `pump()` is now the only place that starts downloads (ADR-0013).
  46 new tests (389 in total).
- M5b: dynamic splitting (a free connection takes over half of the part with the most left;
  `DownloadSettings.dynamic_splitting`), and the connection count in the window's status
  ("Downloading · 8 connections"). Spec FEAT-004; 6 new tests (343 in total).
- M5a, segmented downloads: big files from servers that support ranges and give a version tag
  are downloaded over up to 8 connections at once (parts of at least 1 MiB, files of at least
  2 MiB). Parts are accepted only from exact `206` replies; doubt falls back to one connection;
  a dropped part retries only its own range. One pre-sized, sparse partial file. The parts map
  is saved (history schema version 3) after an off-thread `fsync`, so split downloads pause,
  survive a crash, and resume part by part (ADR-0012). New `sdm.core.segments` and
  `sdm.engine.segmented`.
- `MockServer.ranged`: bounded ranges, per-connection `rate`, `wrong_range_at`, `cut_once`,
  `changed_after`. 44 new tests (337 in total).
- M4b, the window: Pause, Resume (Retry for failed downloads), Resume all, and Cancel for
  paused entries. A question before pausing on a server that can't resume. Status tooltips
  say whether Resume continues or starts over. The status bar counts paused downloads.
  Spec FEAT-003; 5 new tests (293 in total).
- Tests: `no_blocking_dialogs` fixture (an unexpected message box fails instead of hanging).
- M4a, resume: downloads continue from their partial file with `Range` + `If-Range` (ETag or
  Last-Modified), or a 64-byte overlap check when the server gives no version tags. Only an
  exact `206` continues; anything else restarts cleanly (ADR-0011). Retries continue instead
  of restarting. New `paused` state; pause keeps the partial file, cancel deletes it, quitting
  pauses. Interrupted, paused and failed entries can be resumed. History schema version 2
  (partial-file path, version tags, resumable), upgraded in place. Controller `pause`,
  `resume`, `resume_all`; manager `pause` and `PartialSaved`/`Paused` events.
- `MockServer.ranged` test route; 45 new tests (288 in total).
- M3b, the window: Add URL dialog (Ctrl+N) with a "you downloaded this before" warning, a
  live download table (name, size, percent, speed, time left, status), Cancel, Remove from
  list (keeps the file), a status bar summary, a question before quitting with downloads
  running, and startup notices for interrupted entries or a recovered history. New
  modules: `sdm.ui.controller`, `sdm.ui.download_model`, `sdm.ui.add_url_dialog` and
  `sdm.ui.engine_adapter`. `sdm.app` now opens the history and starts the engine. Spec
  FEAT-002; 25 new tests (234 in total).
- M3a, downloads in the background with a history: `DownloadManager`
  (`sdm.engine.manager`) runs downloads on its own thread with an asyncio loop. At most 3 run
  at once, and it reports `Started`, `FileInfo`, `Progress`, `Finished`, `Failed` and
  `Cancelled` events (ADR-0009). The SQLite history (`sdm.storage.database`) lives in
  `%LOCALAPPDATA%\SDM\sdm.db`, with schema versions, a set-aside for corrupted files, and
  crash leftovers marked interrupted (ADR-0010, data-model.md). There is also a speed and
  time-left calculator (`sdm.core.progress`) and download states (`sdm.core.downloads`).
- `download(..., on_file_info=)` reports the file name and size as soon as the server
  answers.
- `MockServer.trickle` test route; 53 new tests (209 in total).
- Scenario server (`scripts/idm_scenarios/server.py`), for re-running the IDM comparison with
  precise evidence: each log line now also has `start` and `end` (date, time and
  milliseconds), `duration_s`, a connection number `conn`, the client's port and
  `disconnected`. New route `/slow-stream.bin`: 3 MiB with no `Content-Length` over about
  90 s, to watch a download's progress. The six M2 routes send byte-for-byte the same
  responses. Planned re-runs R1 (Scenario 5 with the slow stream) and R2 (Scenario 6, every
  click written down) are in `docs/research/behavior-observations.md`. 11 new tests (156 in
  total).
- M2 IDM comparison: OBS-001 to OBS-006 in `docs/research/behavior-observations.md`, with an
  evidence table, request-log analysis, an IDM vs SDM table, findings and missing-evidence
  notes. The parity matrix, IDM feature inventory, FEAT-001, ADR-0008 and roadmap are updated
  from it, and M2 is marked done.
- `DownloadResult.verified_complete`: `False` when only the connection closing marked the end
  of the download, so a cut can't be told apart from success. `sdm-get` prints a warning in
  that case (from OBS-005), and `run_sdm.py` reports it.
- `MockServer.chunked` route for tests, and 6 new tests (145 in total).
- M2 single-connection downloader (`sdm.engine.http_download`), built on aiohttp: http/https
  only, manual redirects (at most 10, each re-checked), 200-only success, 3 attempts with
  backoff and `Retry-After`, `Accept-Encoding: identity`, size verification, free-space check,
  `.sdmpart` temporary files, and cleanup on failure or cancellation.
- Network policy (`sdm.engine.policy`): blocks this computer, link-local/metadata, multicast
  and reserved addresses; private networks only with `--allow-local-network`. Hostnames are
  checked after DNS, inside aiohttp's resolver.
- Safe Windows filenames (`sdm.core.filenames`): `Content-Disposition` (`filename*` too), URL
  fallback, path traversal and device names neutralized, bidi spoofing removed, path-length
  limit respected. Never overwrites: `name (1).ext`.
- Readable errors (`sdm.core.errors`), including Controlled Folder Access's misleading
  "file not found".
- `sdm-get` command: `uv run sdm-get URL [--dest FOLDER] [--allow-local-network] [-v]`.
- Local scriptable mock HTTP server for tests; 135 new unit, integration and security tests
  (139 in total).
- `scripts/bench_http_clients/`: the reproducible httpx vs aiohttp evaluation (ADR-0006).
- Docs: ADR-0006 to 0008, spec FEAT-001, and updated security model, architecture, test
  strategy, parity matrix and roadmap.

- M1 project skeleton: `src/sdm` packages (`core`, `engine`, `storage`, `scheduler`, `bridge`,
  `ui`), a `pyproject.toml` managed with uv, and Python 3.12 as the minimum version.
- Main window with an empty download list (file name, size, progress, speed, time left,
  status), a File → Exit menu and a status bar. It can't download anything yet.
- pytest + pytest-qt smoke tests running off-screen, and ruff lint/format configuration.
- Project documentation: brief, roadmap, feature-parity matrix, architecture, security model,
  test strategy, decision records, and the M0 environment report.

### Changed

- Security (M10a): IPv4 addresses hidden in NAT64 and 6to4 IPv6 addresses are now checked as
  IPv4; the browser pipe refuses clients on other computers.
- Fixed (found by fuzzing, M10a): a browser message with a list as `source`, file names with
  lone UTF-16 surrogates, and malformed addresses such as `http://[` (in Add URL, the
  https-to-http check and redirects) caused unexpected errors instead of clean refusals.
- Fixed (M9 demo): the status bar went blank after the mouse passed over a toolbar button or
  menu item; the status now stays in a permanent label.
- Extension 0.2.1: capture runs before Chrome's Save As, a download handed back to Chrome is
  never captured again (0.2.0 could make Save As reappear in a loop), and the toolbar panel
  shows the last problem.
- Docs: the M7 "host not found" was caused by registering from Claude's sandboxed shell, not by
  Chrome needing a restart; the owner registers the host from their own terminal.
- Every download now refuses a redirect from https to http, as browsers do (M8).
- Resume puts an entry back in the queue (it starts when there's room) instead of starting it
  at once; Start now starts it at once. A temporary failure now waits for an automatic retry
  instead of staying Failed.
- Fixed: a part's reply is checked against the range it requested, not its end after a
  dynamic split (a correct reply used to look wrong and restart the file).
- The quit question now says "Quit and pause them?" (it said partial files would be
  deleted, untrue since M4a). The startup notice for interrupted downloads points to Resume.
- Quitting with downloads running now pauses them (partial files kept, resumable next time)
  instead of cancelling them (M4, ADR-0011).
- An interrupted transfer now says how much arrived: "The download was interrupted after
  2.0 MB of 4.0 MB." (from OBS-006).
- `format_size` moved to `sdm.core.units`, next to new `format_speed` and `format_duration`.
- Scenario server log: when the client hangs up, the line now shows the status that was sent
  and the body bytes really sent, plus `disconnected: true`, instead of `status: 0` and
  `bytes_sent: 0`. Old lines in `logs/idm-requests.jsonl` keep their old meaning.
- 404 and 410 responses now say "The file was not found on the server (...)" instead of
  "The server refused the download (...)" (from OBS-003). Other 4xx errors are unchanged.
