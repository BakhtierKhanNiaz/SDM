# Changelog

All notable changes to SDM are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow semantic versioning
while SDM is in 0.x.

## [Unreleased]

### Added

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
