# Changelog

All notable changes to SDM are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow semantic versioning
while SDM is in 0.x.

## [Unreleased]

### Added

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

- An interrupted transfer now says how much arrived: "The download was interrupted after
  2.0 MB of 4.0 MB." (from OBS-006).
- `format_size` moved to `sdm.core.units`, next to new `format_speed` and `format_duration`.
- Scenario server log: when the client hangs up, the line now shows the status that was sent
  and the body bytes really sent, plus `disconnected: true`, instead of `status: 0` and
  `bytes_sent: 0`. Old lines in `logs/idm-requests.jsonl` keep their old meaning.
- 404 and 410 responses now say "The file was not found on the server (...)" instead of
  "The server refused the download (...)" (from OBS-003). Other 4xx errors are unchanged.
