# System architecture

Status: **M1 skeleton.** Only the UI package has code; the others are empty placeholders
with their responsibilities defined.

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

## Decided later

- Concurrency model: threads vs asyncio, tied to the HTTP library choice (M2).
- How engine progress reaches the UI without blocking it (M3).
- Database schema ([data-model.md](data-model.md), M3).
- Native messaging host packaging and registration (M7).
