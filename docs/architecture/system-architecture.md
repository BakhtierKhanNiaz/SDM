# System architecture

Status: **M2.** `core` (errors, URLs, filenames), `engine` (single-connection downloader,
network policy) and the `sdm-get` command line have code. `ui` shows an empty window.
`storage`, `scheduler` and `bridge` are still placeholders.

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

`sdm.engine.http_download.download(url, folder, policy=, settings=, on_progress=)` is an
`async` function. One call is one download, built on aiohttp (ADR-0006):

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

## Decided later

- How the window runs the engine: a background thread with its own event loop, with
  progress delivered to the UI thread through Qt signals (M3).
- Database schema ([data-model.md](data-model.md), M3).
- Native messaging host packaging and registration (M7).
