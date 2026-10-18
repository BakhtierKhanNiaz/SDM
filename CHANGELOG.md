# Changelog

All notable changes to SDM are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow semantic versioning
while SDM is in 0.x.

## [Unreleased]

### Added

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
