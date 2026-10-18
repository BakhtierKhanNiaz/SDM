# Architecture decision records

Each record states one decision, why it was made, and what it costs. Records are never
deleted. A changed decision gets a new record that supersedes the old one.

---

## ADR-0001: Python + PySide6 desktop application

- **Date:** 2026-10-17 · **Status:** Accepted
- **Context:** The brief asks for a Windows desktop app built with free tools, maintainable by a
  beginner, running well on an i3-8100 with 8 GB RAM and no GPU.
- **Decision:** Python with PySide6 (Qt for Python) for the UI. Use the
  `PySide6-Essentials` package (core Qt modules, including widgets) rather than full `PySide6`,
  which adds large optional modules (WebEngine, 3D, charts) that SDM doesn't need.
- **License:** PySide6 is LGPL-3.0. That's fine for personal use; we use it unmodified, as a
  library.
- **Consequences:** about 80 MB download for Qt. If a later feature needs an Addons module, we
  switch to the full `PySide6` package.

## ADR-0002: Python version policy

- **Date:** 2026-10-17 · **Status:** Accepted
- **Context:** The brief names Python 3.12 as the baseline. Only Python 3.14.7 is installed. All
  chosen dependencies ship Windows wheels for 3.12 through 3.14.
- **Decision:** Develop on 3.14 (`.python-version`). Declare `requires-python = ">=3.12"`. Ruff
  targets `py312`, so it won't suggest syntax newer than 3.12.
- **Consequences:** A feature added in 3.13 or 3.14 (a new library function, for example)
  could slip in unnoticed. Mitigation: before packaging (M10), or earlier if needed, run the tests
  on 3.12 with `uv run --python 3.12 pytest`.

## ADR-0003: uv for environments and dependencies

- **Date:** 2026-10-17 · **Status:** Accepted
- **Context:** We need an isolated environment, reproducible versions, and commands that work
  in PowerShell where script execution (venv activation) is restricted.
- **Decision:** uv (MIT/Apache-2.0, already installed) manages `.venv`, dependencies and the
  `uv.lock` lockfile. Build backend: `uv_build`. Commands run through `uv run`. `link-mode =
  "copy"` because uv's cache (C:) and the project (D:) are on different drives.
- **Consequences:** Contributors need uv. `uv.lock` is committed and pins exact versions.

## ADR-0004: `src/` layout with independent packages

- **Date:** 2026-10-17 · **Status:** Accepted
- **Context:** The brief requires UI, engine, storage, scheduler and bridge to stay independent.
- **Decision:** Code lives in `src/sdm/` with one package per area. The dependency rules are in
  [system-architecture.md](../architecture/system-architecture.md); the key rule is that the
  engine never imports Qt. The `src/` layout means tests run against the installed package, not
  stray files in the project root. Placeholder folders the brief lists (`extension/chrome/`,
  `scripts/`, `tests/integration/`, `tests/security/`) are created when their first file exists,
  because Git doesn't track empty folders.
- **Consequences:** You must run `uv sync` once before the code can be imported. `uv run` does
  this automatically.

## ADR-0005: Project location outside protected folders

- **Date:** 2026-10-17 · **Status:** Accepted
- **Context:** Windows Defender Controlled Folder Access blocks unrecognized programs (Python,
  uv, Git) from writing to Documents and Desktop. Changing that security setting is left to
  the user.
- **Decision:** The repository lives at `D:\Projects\SDM`.
- **Consequences:** None for the code. SDM itself will face the same block if users choose
  protected download folders (handled in M2 error reporting).

## ADR-0006: aiohttp and an asyncio download engine

- **Date:** 2026-10-17 · **Status:** Accepted (approved by the project owner)
- **Context:** The brief left the HTTP library open: httpx or aiohttp. Evaluated on this
  machine with `scripts/bench_http_clients/run.py` (see its docstring for the command; a
  256 MiB file over loopback, test
  server in a separate process; the numbers below are from the committed script's run).

  | Criterion | httpx 0.28.1 | aiohttp 3.14.5 |
  |---|---|---|
  | Latest stable release | 2024-12-06; 1.0 rewrite only as dev pre-releases | 2026-10-11, releases every few weeks |
  | CPU-seconds per GB, 1 connection | 1.56 (sync), 2.69 (async) | 1.12 |
  | CPU-seconds per GB, 8 range segments | 1.75 (sync), 2.62 (async) | 1.12 |
  | Loopback throughput | 381–832 MB/s | 879–901 MB/s |
  | Check resolved IPs just before connecting | Only by replacing the private `_pool` attribute | Public `TCPConnector(resolver=...)` hook |
  | Cancel a stalled read | Works (0.00 s sync close, 0.017 s async) | Works (0.001 s) |
  | API | sync and async | async only |
  | Dependencies | 5 pure-Python | 7; 4 compiled, wheels for cp312–cp314 |

- **Decision:** Use aiohttp. The engine is written with `asyncio`; one download is one
  coroutine (`sdm.engine.http_download.download`).
- **Why:** The connect-time IP check is central to the security model (ADR-0007), and aiohttp
  supports it through a public API. aiohttp is actively maintained and costs the least CPU
  per GB. Speed alone would not decide it: at 100 Mbps every option uses 1–3% of one core.
  Cancellation turned out not to be a differentiator.
- **Consequences:** Async is new to the project owner, so it is introduced step by step. The
  UI (M3) will run the engine's event loop in a background thread. File writes currently
  happen in the event loop thread (fast for one download); revisit if M5's parallel segments
  show the loop stalling on disk writes.

## ADR-0007: Network destination policy

- **Date:** 2026-10-17 · **Status:** Accepted (approved by the project owner)
- **Context:** A link, redirect or DNS answer can point a downloader at this computer, the
  router or another device on the local network (server-side request forgery).
- **Decision:** `sdm.engine.policy.NetworkPolicy`:
  - Always blocked: link-local (including cloud metadata `169.254.169.254`), multicast,
    unspecified (`0.0.0.0`, `::`) and reserved addresses.
  - Blocked unless allowed: this computer (loopback; only tests allow it) and private or
    other non-public ranges (`allow_local_network`, the `--allow-local-network` flag).
  - IP literals are checked before every request, including each redirect hop. Hostnames
    are checked inside aiohttp's resolver, so the checked addresses are exactly the ones
    aiohttp connects to. If any resolved address is blocked, the host is refused.
  - Redirects are followed by hand (at most 10), and each hop is re-validated: only
    http/https, no embedded credentials.
  - Proxy environment variables are ignored (`trust_env=False`): a proxy would hide the real
    destination from the check.
- **Consequences:** By default, SDM can't download from a NAS or router without the flag.
  Known gaps for later hardening: IPv4 addresses embedded in NAT64 (`64:ff9b::/96`) or 6to4
  (`2002::/16`) IPv6 addresses are not unwrapped, and https→http redirects are allowed.

## ADR-0008: File naming and no-overwrite policy

- **Date:** 2026-10-17 · **Status:** Accepted (approved by the project owner)
- **Context:** The brief forbids overwriting existing files without an explicit policy.
  Filenames come from untrusted headers and URLs.
- **Decision:**
  - Name source: `Content-Disposition` (`filename*` before `filename`, per RFC 6266), then
    the last segment of the final URL after redirects, then `download`.
  - Sanitized to one Windows path component: folders stripped (`../`, `\`), invalid and
    control characters replaced with `_`, bidirectional-text controls removed, trailing dots
    and spaces removed, device names prefixed (`CON` → `_CON`), and the length capped so the
    full path, including the `.sdmpart` and ` (999)` suffixes, fits within 259 characters.
  - The download streams into `<name>.sdmpart`, created with exclusive mode (`"x"`), so it
    never reuses another download's partial file.
  - On success, the partial file is renamed with `os.rename`, which on Windows refuses to
    replace an existing file. If the name is taken, SDM tries `name (1).ext` up to
    `name (999).ext`, like Chrome and Windows Explorer. Renames blocked by antivirus locks
    are retried for about 1.5 s.
  - On failure or cancellation, the partial file is deleted. Resume (M4) will change this.
- **Consequences:** Downloading the same URL twice gives `file.zip` and `file (1).zip`.
  IDM, observed in M2 (OBS-002), asks first. It offers a numbered name (`file_2.zip`),
  overwriting, or showing/resuming the existing download. SDM keeps this decision. It can't
  ask until it has a download list (M3), and a "this URL is already in your history" prompt
  is a candidate for M9.

## ADR-0009: The engine runs on its own thread; the window gets events through Qt signals

- **Date:** 2026-10-18 · **Status:** Accepted (M3 plan approved by the project owner)
- **Context:** A window that waits on the network freezes. The engine is asyncio-based
  (ADR-0006) and must never import Qt; the window is Qt and must only be touched from its
  main thread.
- **Decision:** `sdm.engine.manager.DownloadManager` owns one background thread
  (`sdm-engine`) with its own asyncio event loop. Other threads call only `submit`, `cancel`
  and `shutdown`, which hand work to the loop with `call_soon_threadsafe`. The manager reports
  through plain event objects (`Started`, `FileInfo`, `Progress`, `Finished`, `Failed`,
  `Cancelled`), called on the engine thread. The window's adapter (M3b) re-emits them as Qt
  signals, which Qt delivers to the main thread. Only the main thread writes to the database.
- **Details that matter:**
  - At most 3 downloads run at once (an `asyncio.Semaphore`); the rest wait in submission
    order. Real queue management is M6.
  - Progress events are limited to about 5 a second per download. An update held back is
    sent when its slot comes up, and none is sent after the final event.
  - Cancellation is reported from the task's done-callback: a task cancelled before its first
    turn never runs its own code, so an `except CancelledError` inside it would miss it (found
    by `test_cancelling_a_waiting_download`).
- **Consequences:** All engine logic stays testable without Qt
  (`tests/integration/test_manager.py`). The price is one hop (a signal) between an event and
  the screen.

## ADR-0010: Download history in SQLite under %LOCALAPPDATA%

- **Date:** 2026-10-18 · **Status:** Accepted (approved by the project owner)
- **Context:** M3 needs a history that survives restarts and crashes. M4's resume will need
  the URL and progress of unfinished downloads.
- **Decision:** Python's built-in `sqlite3` (no new dependency). File:
  `%LOCALAPPDATA%\SDM\sdm.db`. Full URLs are stored (owner's decision) because resume needs
  them. They stay on this PC, in a per-user folder, and are never logged. WAL journal mode;
  the schema version is in `PRAGMA user_version`; every query uses `?` parameters, never
  string formatting with input. Corrupted files are renamed aside, never deleted. Schema and
  states: [data-model.md](../architecture/data-model.md).
- **Consequences:** Anyone who can read this user's AppData can read the download URLs, the
  same as browser history. If secrets in URLs become a concern, encrypting the column is
  possible later without changing the rest.

## ADR-0011: Resume rules, and what happens to partial files

- **Date:** 2026-10-19 · **Status:** Accepted (M4 plan approved by the project owner)
- **Context:** M3 threw partial files away on any interruption. The brief requires resume
  validation, ETag/Last-Modified handling, verifying response ranges, and never assembling
  inconsistent file versions. OBS-006 showed IDM resuming with `Range` from 64 bytes before the
  end of its data, and giving up when a server answered `200`.
- **Decision:**
  - Resume request: `Range: bytes=N-`, plus `If-Range` with a strong ETag, else Last-Modified.
    Without version tags: request from N−64 and compare those 64 bytes with the end of the
    partial file (our own design, prompted by the OBS-006 observation).
  - A reply continues the file **only** if it is `206` with a `Content-Range` of exactly
    `N-(total−1)/total`, the total matches the known size, and any ETag/Last-Modified it sends
    matches. A `416` with everything already on disk finishes the download. Anything else,
    including a `200`, a wrong range, a changed size or tag, or a failed overlap check, restarts
    from byte 0 in the same partial file.
  - Automatic retries also continue instead of restarting.
  - Pause keeps the partial file; cancel deletes it. Shutting down pauses everything, so it can
    be resumed next time. Nothing resumes automatically at startup. A failed download keeps
    its partial file only if the server can resume (advertised or proved).
  - A partial-file path from the database is used, or deleted, only if it is a `.sdmpart` file
    directly inside that entry's download folder.
  - `sdm-get` keeps M2's behavior: any failure deletes the partial file.
- **Consequences:** Interruptions no longer waste what already arrived (verified: bytes sent
  across retries add up to exactly the file size). Paused partial files take disk space until
  resumed or cancelled. A server that lies about ranges just causes a restart, never a corrupt
  file (`tests/integration/test_resume.py`).

## ADR-0012: Segmented downloads

- **Date:** 2026-10-19 · **Status:** Accepted (M5 plan approved by the project owner)
- **Context:** The brief asks for parallel segmented downloads "when the server supports them",
  with range validation, ETag/Last-Modified handling, and never assembling inconsistent file
  versions. OBS-001: IDM used 8 connections for a 1 MiB file (1 plain + 7 `Range` attempts,
  start points halving, no `If-Range`) and dropped them on `200`. OBS-004: its extra
  connections went to the final URL after a redirect.
- **Decision:**
  - Split only when the file is at least 2 MiB, the server advertises `Accept-Ranges: bytes`
    and gives a strong ETag or Last-Modified. Parts are at least 1 MiB; up to 8 connections per
    download (owner's decisions; IDM splits more eagerly and without version tags).
  - The first connection is the ordinary request and downloads part 1 from byte 0. The extra
    connections ask for `bytes=a-b` with `If-Range`, at the final URL (as IDM did, OBS-004).
    Every request goes through the redirect checks and the network policy.
  - A part is accepted only from a `206` with `Content-Range` exactly `a-b/total` and the same
    version tags. A temporary error (5xx, 408, 429) retries the part.
  - Fallback: if an extra part's first reply can't be trusted, or it can't connect, while the
    first connection is still open, the extras stop and the first connection carries on to the
    end (its reply is the whole file). The first connection waits at the end of its part until
    every extra is confirmed, so fallback is always possible until then. After that, an
    untrusted reply means the file changed: download again on one connection.
  - A dropped part retries only its own remaining range; the others continue.
  - One pre-sized partial file, marked sparse on NTFS (otherwise Windows zero-fills up to every
    far write, which can block for seconds). All parts write through one file handle.
  - The parts map is saved about once a second: written data is flushed and `fsync`ed first,
    on a worker thread, and only then is the map reported. On the event loop thread, `fsync`
    on a busy disk stalled every connection (seen as a flaky speed test during full runs:
    1.8–2.4 s instead of 1.0 s; 1.04 s after the fix).
  - Resume continues every unfinished part with its own range. A damaged or mismatched map
    starts over; it is never read as "complete" or as a prefix.
- **Consequences:** Against a per-connection limit of 100 KB/s, 4 connections took 1.02 s
  against 4.02 s for one (`test_split_download_beats_a_per_connection_speed_limit`). Servers
  without version tags download on one connection.
- **M5b addition, dynamic splitting:** whenever a connection is free (a part finished, or a
  resume has fewer unfinished parts than connections allowed), the part with the most bytes
  left gives its second half to a new connection, if both halves keep at least 1 MiB (ties:
  the earliest part). It runs only once every part is confirmed, so fallback stays simple.
  A resume halves repeatedly, the shape OBS-001 suggested for IDM. A part's reply is checked
  against the range it actually requested: a split can shrink the part while the request is
  in flight (a bug found by `test_a_connection_that_finishes_early_helps_the_slowest`).
  `DownloadSettings.dynamic_splitting` can switch it off.

## ADR-0013: The queue is planned outside the engine

- **Date:** 2026-10-19 · **Status:** Accepted (M6 plan approved by the project owner)
- **Context:** Until M5 the engine decided who runs next (first in, first out, at most 3).
  M6 needs a reorderable queue, a changeable limit, a schedule, "Start now" and automatic
  retries. IDM: categories by file type with folders (OBS-001/002/005); its OBS-006 message
  offers a queue that retries from the start until success. IDM's queue and scheduler screens
  were not observed.
- **Decision:**
  - `sdm.scheduler.queue.plan_queue` (pure, clock passed in) decides what to start and what to
    send back to waiting. The controller's `pump()` is the only code that submits to the
    engine; it runs after every event and action and every 30 s. The engine's own limit is
    raised to 32 as a safety net.
  - One queue, ordered by `queue_position`. Limit 1-8 (default 3). "Start now" ignores the
    limit and the schedule. "Add without starting" adds the entry paused.
  - Schedule: start and stop times plus days; an overnight window belongs to the day it
    starts on; equal times mean the whole day. Outside the window running queue downloads go
    back to waiting with their partial file. The scheduler only starts and pauses downloads:
    no shutdown or sleep (owner's decision).
  - Pauses made by the planner (schedule, lower limit) return the entry to *waiting*; the
    user's Pause makes it *paused* (the planner ignores it).
  - Automatic retries for temporary failures (network, timeout, 5xx): after about 1, 5 and
    15 minutes, resuming each time; a manual Resume or Retry resets the count. Permanent
    failures (404) aren't retried.
  - Categories (General, Compressed, Documents, Music, Video, Programs) are labels from the
    file extension. An optional setting (off by default) saves into `<folder>\<Category>`,
    created when its first download starts; the category comes from the URL at that point.
  - Settings live in the history's new `settings` table. Quitting still pauses everything and
    nothing starts on its own at the next launch (M4 rule): queue order, settings and retry
    counts survive, and Resume all continues in order.
- **Consequences:** The queue logic is tested without Qt or a network (`test_queue_planner.py`,
  fake clock in `test_queue.py`). A schedule only acts while SDM is running.
