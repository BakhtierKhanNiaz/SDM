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
  IDM's own behavior has not been observed yet; we compare in the M2 IDM comparison.
