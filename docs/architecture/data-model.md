# Data model

Status: **not designed yet.** The SQLite schema is designed in M3, when downloads and history
first need to be persisted.

Decisions to make in M3:

- Tables for downloads (URL, destination, size, state, timestamps, validators such as ETag and
  Last-Modified) and, from M5, per-segment progress.
- The download state machine (queued, downloading, paused, completed, failed, cancelled) and the
  allowed transitions.
- Schema versioning and migrations, so upgrades never lose history.
- Where the database lives (expected under `%LOCALAPPDATA%\SDM\`, outside protected folders).
- What is never stored: cookies, authorization headers and other secrets, unless a later
  decision explicitly allows it with protection.
