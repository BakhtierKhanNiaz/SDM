# Changelog

All notable changes to SDM are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow semantic versioning
while SDM is in 0.x.

## [Unreleased]

### Added

- M1 project skeleton: `src/sdm` packages (`core`, `engine`, `storage`, `scheduler`, `bridge`,
  `ui`), a `pyproject.toml` managed with uv, and Python 3.12 as the minimum version.
- Main window with an empty download list (file name, size, progress, speed, time left,
  status), a File → Exit menu and a status bar. It can't download anything yet.
- pytest + pytest-qt smoke tests running off-screen, and ruff lint/format configuration.
- Project documentation: brief, roadmap, feature-parity matrix, architecture, security model,
  test strategy, decision records, and the M0 environment report.
