# Test strategy

## How to run

```powershell
uv run pytest                 # everything
uv run pytest tests/unit -v   # one folder, verbose
uv run ruff check .           # lint
uv run ruff format --check .  # formatting
```

Qt runs off-screen during tests (`QT_QPA_PLATFORM=offscreen`, set in `tests/conftest.py`), so
no windows appear and the tests don't need a desktop.

## Layers

| Folder | What goes there | When |
|---|---|---|
| `tests/unit/` | Fast tests of one module, no network or real disk beyond `tmp_path` | now |
| `tests/integration/` | Engine against a local mock HTTP server, storage against real SQLite files | from M2 |
| `tests/security/` | Malicious URLs, filenames, redirects, browser messages | from M2 |

## Rules

- No third-party websites in tests. Use a local mock HTTP server bound to `127.0.0.1` and
  synthetic files.
- Tests must be deterministic: no sleeps that race, no dependence on real time where avoidable.
- Every bug fix gets a regression test when practical.
- A test is "passing" only if it actually ran and passed. Skipped or not-run tests are reported
  as such.

## Current tests (M1)

`tests/unit/test_main_window.py`: the package is installed; the window opens with an empty
list and the status "No downloads yet"; the list has the six expected columns; File → Exit
closes the window.

## Planned coverage (from the project brief)

Valid/invalid URLs, successful downloads, redirects, network interruption, cancellation, retries,
unknown sizes, resume after restart, unsupported ranges, bad `Content-Range`, remote file
changes, segment failures, filename collisions, disk-write failures (including Controlled Folder
Access), database recovery, malicious browser messages, unsafe redirects and local-network
access, and bridge disconnection.
