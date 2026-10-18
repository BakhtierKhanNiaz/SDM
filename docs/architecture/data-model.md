# Data model

Status: **M3, schema version 1.** Code: `sdm/core/downloads.py` (states, record) and
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
| `created_at`, `updated_at`, `finished_at` | text | ISO 8601 times in UTC |

Index: `downloads_by_url` (for the "you downloaded this before" check).

Never stored: cookies, authorization headers, or any request headers.

## States

```
queued ──▶ downloading ──▶ completed
   │            │
   ├────────────┼──▶ failed
   ├────────────┼──▶ cancelled
   └────────────┴──▶ interrupted   (SDM closed or crashed mid-download)
```

- Every state change goes through `check_transition`; an illegal one raises `ValueError`.
- Finished states (completed, failed, cancelled, interrupted) are final in M3. Downloading the
  same URL again creates a new row. M4 adds paused and resuming from interrupted.
- On startup, rows still `queued` or `downloading` (left by a crash or a forced exit) become
  `interrupted` with the message "SDM was closed before this download finished."
- "Remove from list" deletes the row only, never the downloaded file. Active rows can't be
  removed: cancel first.

## Versions and upgrades

- `PRAGMA user_version` holds the schema version (1 now). Each entry in `_MIGRATIONS` upgrades
  one version, inside its own transaction, so a failed upgrade changes nothing.
- A database made by a newer SDM (higher version) is refused with a message and left untouched.
- A corrupted file ("file is not a database", a failed `quick_check`) is renamed to
  `sdm.db.corrupt-<date>-<time>` (never deleted), and a fresh database is started. The window
  tells the user and names the renamed file.

## Threading

One `DownloadStore` belongs to one thread: the window's main thread. Engine events reach that
thread through Qt signals before anything is written (ADR-0009). SQLite enforces this:
using the connection from another thread raises an error.
