# System architecture

Status: **M3.** `core` (errors, URLs, filenames, units, download states, transfer meter),
`engine` (downloader, network policy, download manager), `storage` (SQLite history) and the
`sdm-get` command line have code. The window (`ui`: controller, table model, Add URL dialog, engine adapter) shows live
downloads and the history (M3b). `scheduler` and `bridge` are
still placeholders.

## Overview

SDM is a single Windows desktop process written in Python, with a PySide6 interface. A Chrome
extension (M7) will talk to it through Chrome Native Messaging, which runs a small host program
over stdin/stdout, never a network port.

```
        Chrome extension (M7)
                │  native messaging (stdin/stdout, JSON)
                ▼
   ┌──────────── bridge ────────────┐
   │ validates every message        │
   └──────────────┬─────────────────┘
                  ▼
   ui ──────▶ scheduler ──────▶ engine ──▶ HTTP servers
    │              │               │
    └──────────────┴──▶ storage ◀──┘   (SQLite)

   core: shared types, settings, paths, logging (used by all)
```

## Packages and dependency rules

| Package | Responsibility | May import |
|---|---|---|
| `sdm.core` | Domain types, settings, paths, logging helpers | standard library only |
| `sdm.engine` | HTTP downloads, progress, retries, resume, segments | `core` (**no Qt**) |
| `sdm.storage` | SQLite persistence, schema migrations | `core` |
| `sdm.scheduler` | Queues, start/stop times, concurrency limits | `core`, `engine`, `storage` |
| `sdm.bridge` | Native messaging host, message validation | `core` (hands validated requests to the app) |
| `sdm.ui` | Windows, dialogs, tray, notifications | everything above, plus PySide6 |

Why the engine must not import Qt: it can then be tested quickly without a GUI, reused by the
native messaging host, and kept free of UI-thread concerns. The UI will receive engine events
through a thin adapter layer in `ui`.

## Entry points

- `app.py` (source checkout) → `sdm.app.main()` → creates the `QApplication` and `MainWindow`.
- The `sdm` GUI script in `.venv\Scripts\` (from `[project.gui-scripts]`) calls the same function.
- `sdm-get` (from `[project.scripts]`) → `sdm.cli.main()` → runs one download with
  `asyncio.run`. It sits outside `ui` because it uses no Qt.

## The download engine (M2)

`sdm.engine.http_download.download(url, folder, policy=, settings=, on_progress=,
on_file_info=)` is an `async` function. One call is one download, built on aiohttp (ADR-0006):

```
download()
  └─ attempt loop (≤ 3 attempts, backoff, Retry-After)
       └─ _attempt()
            ├─ follow redirects by hand ─ each hop: validate_url + policy.check_url_host
            │                              connect: PolicyResolver checks resolved IPs
            ├─ check status (200 only)
            ├─ choose + sanitize filename, check free space
            ├─ stream into "<name>.sdmpart" (exclusive create), report progress
            ├─ verify size, rename without overwrite → "<name>" or "<name> (n)"
            └─ any failure or cancellation → delete the .sdmpart file
```

Library and OS exceptions are translated in one place (`_translated_errors`) into
`DownloadError`s with user-readable messages and a `retryable` flag.

**Concurrency:** `asyncio`. Cancelling the task (`task.cancel()`) stops a download promptly.
File writes run in the event loop thread for now (ADR-0006 consequences).

## The download manager and history (M3, ADR-0009 and ADR-0010)

```
 main thread (Qt)                               engine thread "sdm-engine" (asyncio)
 ┌──────────────────────────┐  submit/cancel   ┌──────────────────────────────────────┐
 │ window + DownloadStore   │ ───────────────▶ │ DownloadManager                      │
 │ (only writer to SQLite)  │                  │  semaphore: at most 3 run at once     │
 │                          │ ◀── events ───── │  one task per download → download()  │
 └──────────────────────────┘  via Qt signals  └──────────────────────────────────────┘
```

- Events: `Started`, `FileInfo`, `Progress` (at most ~5/s, the last one always delivered),
  `Finished`, `Failed`, `Cancelled`. They are called on the engine thread; M3b's adapter turns
  them into Qt signals.
- `DownloadStore` (`sdm.storage.database`) keeps the history in
  `%LOCALAPPDATA%\SDM\sdm.db`. Schema and states: [data-model.md](data-model.md).
- `TransferMeter` (`sdm.core.progress`) turns progress into speed and time left, averaged over
  3 s.

## Decided later

- Native messaging host packaging and registration (M7).

## Resume (M4, ADR-0011)

```
attempt
  ├─ partial file with N trusted bytes?  no ─▶ plain GET
  │                                      yes ─▶ GET + Range: bytes=N- (+ If-Range tag)
  │                                             or bytes=(N-64)- without tags
  ├─ 206 + exact Content-Range (+ same tags, + 64-byte overlap matches) ─▶ append from N
  ├─ 416 and N == total ─▶ already complete: finish
  └─ anything else (200, wrong range, changed size/tag, overlap mismatch) ─▶ restart at 0
```

`download(..., resume_from=, keep_partial=, on_partial=)`: `on_partial` reports the partial
file and version tags (the manager's `PartialSaved` event; the controller stores them). The
manager's `pause()` keeps the partial file (`Paused` event); `cancel()` deletes it. `shutdown()`
pauses everything.
