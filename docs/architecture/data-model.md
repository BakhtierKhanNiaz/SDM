# Data model

Status: **M4, schema version 2.** Code: `sdm/core/downloads.py` (states, record) and
`sdm/storage/database.py` (SQLite). Decisions: ADR-0010.

## Where it lives

`%LOCALAPPDATA%\SDM\sdm.db` (for this user: `C:\Users\<you>\AppData\Local\SDM\sdm.db`). That
folder is private to the Windows user and outside Controlled Folder Access's protected folders.
SQLite runs in WAL mode, so `sdm.db-wal` and `sdm.db-shm` appear next to it while SDM runs.

## Table `downloads`

| Column | Type | Meaning |
|---|---|---|
| `id` | integer, primary key | Never reused (`AUTOINCREMENT`) |
| `url` | text | The full URL as entered. **It can contain access tokens**: it stays in this file and is never logged (logs use `redact_url`) |
| `folder` | text | Download folder chosen for this entry |
| `allow_local_network` | 0/1 | The network-policy choice for this entry (ADR-0007) |
| `state` | text | One of the states below (enforced by a `CHECK` constraint) |
| `file_name` | text, null | Name chosen once the server answered; the final name (with any ` (1)`) once completed |
| `path` | text, null | Full path of the finished file |
| `total_bytes` | integer, null | Size from the server; null when unknown |
| `received_bytes` | integer | Bytes received, saved at most about once a second while downloading |
| `verified_complete` | 0/1, null | 0 when only the connection closing marked the end (OBS-005) |
| `error` | text, null | The user-readable message for failed and interrupted entries |
| `created_at`, `updated_at`, `finished_at` | text | ISO 8601 times in UTC (`finished_at`: when it stopped, also for paused) |
| `part_path` | text, null | The `.sdmpart` file while unfinished (M4). Only trusted if it is a `.sdmpart` file directly in `folder` |
| `etag`, `last_modified` | text, null | The server's version tags, sent back with `If-Range` when resuming (M4) |
| `resumable` | 0/1 | The server advertised (`Accept-Ranges: bytes`) or proved (a `206`) that it can resume (M4) |

Index: `downloads_by_url` (for the "you downloaded this before" check).

Never stored: cookies, authorization headers, or any request headers.

## States

```
queued ──▶ downloading ──▶ completed
  ▲ │           │
  │ ├───────────┼──▶ paused ──────┐     (partial file kept)
  │ ├───────────┼──▶ failed ──────┤     (partial kept only if the server can resume)
  │ ├───────────┼──▶ interrupted ─┤     (SDM closed or crashed mid-download)
  │ └───────────┴──▶ cancelled    │     (partial file deleted)
  └───────────────────────────────┘     resume / retry
```

- Every state change goes through `check_transition`; an illegal one raises `ValueError`.
- Paused, failed and interrupted entries can be resumed (back to queued) or cancelled (their
  partial file is deleted). Completed and cancelled are final: downloading the same URL again
  creates a new row.
- On startup, rows still `queued` or `downloading` (left by a crash or a forced exit) become
  `interrupted` with the message "SDM was closed before this download finished." Their partial
  file stays recorded, so they can be resumed. Nothing resumes on its own (owner's decision).
- "Remove from list" deletes the row and, for an unfinished entry, its partial file. A
  finished download's file is never touched. Active rows can't be removed.

## Versions and upgrades

- `PRAGMA user_version` holds the schema version (2 now; version 2 rebuilt the table to
  allow `paused` and add the resume columns, copying every row with its id). Each entry in `_MIGRATIONS` upgrades
  one version, inside its own transaction, so a failed upgrade changes nothing.
- A database made by a newer SDM (higher version) is refused with a message and left untouched.
- A corrupted file ("file is not a database", a failed `quick_check`) is renamed to
  `sdm.db.corrupt-<date>-<time>` (never deleted), and a fresh database is started. The window
  tells the user and names the renamed file.

## Threading

One `DownloadStore` belongs to one thread: the window's main thread. Engine events reach that
thread through Qt signals before anything is written (ADR-0009). SQLite enforces this:
using the connection from another thread raises an error.
