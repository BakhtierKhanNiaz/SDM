# Test strategy

## How to run

```powershell
uv run pytest                     # everything (145 tests, ~35 s)
uv run pytest tests/unit -v       # one folder, verbose
uv run pytest -k redirect         # tests whose name contains "redirect"
uv run ruff check .               # lint
uv run ruff format --check .      # formatting
```

Qt runs off-screen during tests (`QT_QPA_PLATFORM=offscreen`, set in `tests/conftest.py`), so
no windows appear and the tests don't need a desktop.

## Layers

| Folder | What goes there |
|---|---|
| `tests/unit/` | One module at a time, no network: URLs, filenames, policy, Retry-After, CLI, window, units, download states, transfer meter, history database |
| `tests/integration/` | The engine and the `DownloadManager` (engine thread, events, cancel, 3-at-once limit, shutdown), and the window and controller end to end (`test_window_downloads.py`: progress, cancel, history after restart, quitting), all against the local mock server |
| `tests/security/` | Unsafe destinations, hostile redirects and filenames, the CLI refusing this computer |

## The mock server

`MockServer` in `tests/conftest.py` is Python's standard-library `http.server`, running on
`127.0.0.1` with a random port in a background thread. Each test scripts its responses:

```python
# The first request gets a 503, every later one gets the file.
mock_server.add("/flaky", mock_server.status(503), mock_server.file(DATA))
```

Route builders: `ranged` (a resumable server with bounded and open ranges; per-connection
`rate`; faults keyed by a part's start byte: `wrong_range_at`, `cut_once`; and
`changed_after` to swap in a new version of the file; `206`, `Content-Range`, ETag/Last-Modified,
`If-Range`, `416`, and on demand `cut_at`, `stall_at`, a wrong `content_range`, with a `log`
of every request), `file` (with or without `Content-Length`, extra headers), `status`,
`redirect`, `truncated` (promises N bytes, sends half), `chunked` (chunked encoding, complete
or cut before the last chunk), and `stall` (sends a little, then goes silent). `mock_server.hits[path]` counts requests, and `mock_server.requests` keeps their
headers.

Fixtures: `fetch(url, ...)` runs one download into `tmp_path`, with loopback allowed (the
default policy blocks the test server, as it should) and short timeouts.

## Rules

- No test may open a real message box: `no_blocking_dialogs` (autouse, in `conftest.py`)
  makes any unplanned one fail at once instead of hanging the run. Tests that expect a
  dialog patch it themselves.
- Test servers record what they send *before* sending it, so a fast client never makes a
  test read the log too early.

- No third-party websites in tests: local mock server and synthetic data only.
- Deterministic: no timing races, and small timeouts only where the test is about timeouts.
- Simulate what can't be produced safely: disk-full, `PermissionError`, and the Controlled
  Folder Access error are injected with `monkeypatch`.
- Every bug fix gets a regression test when practical.
- A test is "passing" only if it actually ran and passed. Skipped or not-run tests are reported
  as such.

## Coverage vs the brief's list

| Brief item | Status |
|---|---|
| Valid and invalid URLs | Covered (M2) |
| Successful downloads, unknown sizes (with the completeness warning) | Covered (M2) |
| Redirects; unsafe redirects and local-network access | Covered (M2) |
| Network interruption, retry behavior | Covered (M2) |
| Cancellation | Covered (M2 engine; M3a manager: running, waiting, at shutdown) |
| Filename collisions, disk-write failures | Covered (M2) |
| Resume after restart, unsupported ranges, bad `Content-Range`, remote file changes | Covered (M4: `test_resume.py`, `test_window_resume.py`) |
| Concurrent segment failures | Covered (M5: `test_segmented.py`) |
| Database recovery | Covered (M3a: corrupted file set aside, newer schema refused, crash leaves entries interrupted); resume-after-crash in M4 |
| Malicious browser messages, bridge disconnection | M7 |
