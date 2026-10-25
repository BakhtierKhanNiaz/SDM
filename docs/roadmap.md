# Roadmap

Milestones run in order. A milestone is **Done** only when its acceptance criteria have been met
and its tests have actually run and passed.

| Milestone | Goal | Status |
|---|---|---|
| M0 | Inspect the environment, repository and dependencies | Done (2026-10-17) |
| M1 | Project structure, configuration, documentation, initial desktop window | Done (2026-10-17) |
| M2 | Reliable single-connection HTTP downloader | Done (2026-10-18) |
| M3 | Progress, cancellation, history and persistent state | Done (2026-10-19) |
| M4 | Pause/resume and crash recovery | Done (2026-10-19) |
| M5 | Parallel segmented downloads | Done (2026-10-19) |
| M6 | Queue management and scheduling | Done (2026-10-19) |
| M7 | Chrome extension and native messaging bridge | Done (2026-10-19) |
| M8 | Browser handoff integrated with the download engine | Done (2026-10-20) |
| M9 | Interface, settings, notifications and usability | Done (2026-10-20) |
| M10 | Security, performance, regression testing and Windows packaging | Done (2026-10-20) |
| M11 | Open-source release on GitHub (Apache-2.0, UI/UX, more browsers) | Done (2026-10-25; two owner checks open) |
| M12 | Media: video/audio converter (ffmpeg) and optional yt-dlp add-on | In progress (M12a done) |

## M0: Environment inspection (done)

Findings are in [research/environment-m0.md](research/environment-m0.md).

## M1: Project skeleton (done)

Acceptance criteria, all met on 2026-10-17:

- `uv run python app.py` opens the SDM window.
- `uv run pytest` passes (4 tests).
- `uv run ruff check .` and `uv run ruff format --check .` report no problems.
- The work is committed on branch `m1/project-skeleton`.

## M2: Single-connection downloader (done)

Done on branch `m2/single-connection-downloader`:

- HTTP library chosen by measurement: aiohttp (ADR-0006, `scripts/bench_http_clients/`).
- Spec FEAT-001; network policy (ADR-0007); naming and no-overwrite policy (ADR-0008).
- `sdm-get` command line; local mock server; unit, integration and security tests.

Acceptance criteria, all met on 2026-10-18: FEAT-001's tests pass (145 in total), ruff is
clean, and:

- [x] One real-world download (2026-10-17, approved by the owner):
  `uv run sdm-get https://www.python.org/ftp/python/3.14.7/python-3.14.7-embed-amd64.zip -v`
  saved 12,673,227 bytes to `Downloads` in about 3 s. The SHA-256 matched the value python.org
  publishes (`d297e5ff…a6ab1f15`), all 37 zip members passed their CRC checks, and no
  `.sdmpart` file was left behind. Nothing from the zip was run.
- [x] IDM comparison (2026-10-18): the owner ran the six scenarios in IDM by hand. They were
  checked against the scenario server's request log and the SHA-256 of every saved file, and
  recorded as OBS-001 to OBS-006 in
  [behavior-observations.md](research/behavior-observations.md). Two small fixes came out of
  it: a warning when completeness can't be confirmed (unknown size) and a "not found" message
  for 404/410. Not observed, so carried forward: IDM's live progress display for unknown sizes
  (M3) and how many times IDM retries automatically (M4).

Known issue (cosmetic, found in the real-world demo): with `-v`, log lines are printed on the
same line as `sdm-get`'s progress display, because both write to stderr and the progress line
doesn't end with a newline. The downloaded file is unaffected.

## M3: Downloads in the window, with history (done)

Done on branch `m3/window-downloads-history`:

- M3a (`6419fe8`): `DownloadManager` on its own thread (ADR-0009), the SQLite history
  (ADR-0010, data-model.md), and the speed/time-left calculator.
- M3b: the window. Add URL dialog with a "downloaded before" warning, a live table (name, size,
  percent, speed, time left, status), Cancel, Remove from list (keeps the file), a status bar
  summary, a question before quitting with downloads running, and startup notices for an
  interrupted or recovered history. Spec FEAT-002.

Checked on 2026-10-19: 234 tests pass, ruff is clean, and `uv run python app.py` opens and
closes cleanly, creating `%LOCALAPPDATA%\SDM\sdm.db` (schema 1, WAL). A screenshot with real
local downloads showed three running at once, a fourth waiting, and live numbers.

Acceptance criteria, all met on 2026-10-19:

- [x] One real-world download through the window (approved by the owner): python.org's
  `python-3.14.7-embed-amd64.zip`, through the Add URL dialog's checks and the window's
  `add_download`, with the real history and the default network policy. Saved as
  `python-3.14.7-embed-amd64 (1).zip`, because M2's copy was already there; that copy was
  untouched (same SHA-256 and timestamp). 12,673,227 bytes; the SHA-256 matched python.org's
  published value (`d297e5ff…a6ab1f15`); no `.sdmpart` left; the history entry is completed and
  verified. It took 23.9 s: the window itself measured 536 KB/s from the server. The same
  window path moves 261 MB/s over loopback, so the time was the server's and the network's.
  No "downloaded before" warning was shown, as expected: M2's copy came from `sdm-get`, which
  doesn't write to the history.
- [ ] Optional: IDM re-run R1 to compare the live progress display (makes it *Verified*).

## M4: Pause, resume and crash recovery (done)

Done on branch `m4/pause-resume`:

- M4a (`8e41d12`): resume from partial files with `Range` + `If-Range` or a 64-byte overlap
  check; only an exact `206` continues (ADR-0011). Retries continue, the `paused` state is
  added, history schema version 2, and the manager and controller can pause and resume.
- M4b: Pause, Resume (Retry for failed downloads), Resume all, and Cancel for paused entries
  in the window. A question before pausing on a server that can't resume. Quitting pauses
  ("Quit and pause them?"). Startup points to Resume / Resume all. Status tooltips say
  whether Resume continues or starts over. Spec FEAT-003.

Checked on 2026-10-19: 293 tests pass (three full runs), ruff is clean, and
`uv run python app.py` opens and closes cleanly. It upgraded the real history from schema 1
to 2 in place, keeping entry #1. A screenshot with real local downloads showed one paused at
27% beside two running.

Found and fixed while testing:

- The table had no label for `paused` (KeyError while drawing).
- The window didn't learn that a server can resume until the next state change, so Pause
  asked "Pause anyway?" for no reason.
- A race in the test server's request log (written after sending); it is now written before.
- Tests now fail at once on an unexpected message box instead of hanging.

Acceptance criteria, all met on 2026-10-19:

- [x] One real-world pause and resume across a full SDM restart (approved by the owner):
  python.org's `python-3.14.7-embed-amd64.zip`, through the window code with the real history
  and the default policy, in two separate processes. Phase 1: the Add URL dialog showed the
  "already downloaded" warning (naming the `(1)` copy); Pause at 3,932,160 of 12,673,227
  bytes (31%); partial file exactly that size; the server advertised resume, with a strong
  ETag and Last-Modified; SDM quit. Phase 2 (new process): the entry was still paused at
  3,932,160; Resume continued from there (the smallest progress shown afterwards was
  3,932,160, and the engine logged no restart); done in 3.3 s as
  `python-3.14.7-embed-amd64 (2).zip`. The SHA-256 matched python.org's published value; the
  earlier two copies were untouched; no `.sdmpart` left; history entry #2 completed and
  verified.
- [ ] Optional: IDM comparison R2 (automatic retries) and resume against a `206` server.

## M5: Parallel segmented downloads (done)

Done on branch `m5/segmented-downloads`:

- M5a (`b5590ea`): split downloads over up to 8 connections, exact-`206` validation, fallback
  to one connection, per-part retries, a sparse pre-sized partial file, an off-thread `fsync`
  before saving the parts map, history schema version 3, and resume part by part (ADR-0012).
- M5b: dynamic splitting (free connections take over half of the biggest part), the
  connection count in the window ("Downloading · 8 connections"), spec FEAT-004.

Checked on 2026-10-19: 343 tests pass (three full runs), ruff is clean, and
`uv run python app.py` opens and closes cleanly; it upgraded the real history to schema 3 with
both entries kept. With the defaults against a local server limited to 0.4 MB/s per
connection, the window showed "Downloading · 8 connections" at 3.0 MB/s.

Found and fixed while testing:

- `fsync` on the event loop thread stalled every connection on a busy disk (a speed test that
  only failed in full runs); it now runs on a worker thread.
- A part's reply was checked against its end *after* a dynamic split had shrunk it, so a
  correct reply looked wrong and the file restarted.
- The connection count briefly counted a finished part twice.

Acceptance criteria, all met on 2026-10-19:

- [x] One real-world segmented download (approved by the owner): python.org's
  `python-3.14.7-embed-amd64.zip` (12,673,227 bytes) through the window code with the real
  history, default policy and default settings. The window showed up to 8 connections
  (counts seen: 2, 3, 5, 7, 8); the engine logged no fallback, so every part came back as an
  exact `206`. Done in 3.8 s as `python-3.14.7-embed-amd64 (3).zip`; the SHA-256 matched
  python.org's published value; the three earlier copies were untouched; no `.sdmpart` left;
  the history entry is completed and verified, with its parts map cleared.
- [ ] Optional: IDM comparison against a resumable server.

## M6: Queue management and scheduling (done)

Done on branch `m6/queue-scheduling`:

- M6a (`9217188`): the queue planner (order, limit 1-8, schedule, Start now, automatic retries
  after about 1, 5 and 15 minutes), categories, history schema version 4 with a settings
  table; the controller's `pump()` is the only place that starts downloads (ADR-0013).
- M6b: a Queue menu (Start now, Move to top/up/down/bottom), the Scheduler dialog (limit,
  times and days, category subfolders), "Start the download now" in Add URL, and a Category
  column with a filter. Spec FEAT-005.

Checked on 2026-10-19: 395 tests pass (three full runs), ruff is clean, and
`uv run python app.py` opens and closes cleanly; it upgraded the real history to schema 4.
That launch check showed existing entries labelled "General": upgrades now label existing
entries from their file names (the owner's history had already been upgraded, so its three
entries keep "General"). A screenshot showed the limit of 2 holding with three waiting.

Acceptance criteria, all met on 2026-10-19:

- [x] One real-world scheduled download (approved by the owner): python.org's
  `python-3.14.7-embed-amd64.zip` through the window code with the real history and policy,
  and a schedule window of 03:10-03:40. Added at 03:08:31, it waited as Queued; the app's own
  30-second timer (no manual `pump()`) started it at 03:10:01, 1.7 s after the window opened.
  Saved as `python-3.14.7-embed-amd64 (4).zip`, category Compressed; the SHA-256 matched
  python.org's published value; the earlier four copies were untouched. The owner's queue
  settings were saved before the demo and restored afterwards (checked).
- [ ] Optional: observe IDM's queue and scheduler screens (checklist).

## M7: Chrome extension and native messaging bridge (done)

Done on branch `m7/browser-bridge` (ADR-0014, spec FEAT-006):

- `sdm.bridge.protocol`: framing (4-byte length + JSON, 64 KiB cap) and the strict request
  schema. `sdm.bridge.pipe`: the per-user key, the authenticated named pipe, the listener
  and client. `sdm.bridge.host`: the host Chrome starts; it starts SDM if needed.
  `sdm.bridge.install`: registration for one extension ID, and its removal.
- The window: a handoff opens Add URL filled in, one at a time; the pipe makes SDM
  single-instance.
- `extension/chrome`: Manifest V3, "Download with SDM" on links; `node --test` tests.

Checked on 2026-10-19: 485 Python tests pass (90 new), 12 extension tests pass, ruff is
clean. A launch check with a throwaway `LOCALAPPDATA` used the real `sdm.exe` and host
processes: a second SDM exited quietly in 1.2 s; the host handed a link to the running SDM in
0.2 s; with SDM closed, the host started it and got `{"ok": true}` in 1.5 s.

Acceptance, all met on 2026-10-19:

- [x] Register the host (approved by the owner, 2026-10-19): one HKCU value pointing at
  `%LOCALAPPDATA%\SDM\bridge\com.sdm.bridge.json`, allowed origin limited to the owner's
  extension ID. The launcher, run through `cmd.exe` as Chrome does, refused a message with an
  extra field (`bad_request`) and wrote nothing else to stdout.
  **Correction (2026-10-20):** Claude ran this registration from its sandboxed shell. The
  registry value and files were visible only to programs started inside that sandbox, so the
  owner's own Chrome kept answering "host not found" (`reg query` in the owner's terminal
  found no key). The owner then registered it from their own PowerShell, which fixed it.
  Registration must be run by the owner, in their own terminal.
- [x] Chrome finds and runs the registered host (2026-10-19). A throwaway Chrome started from
  Claude's shell found it: an invalid link got `bad_request`, and a valid one started SDM
  (throwaway data) and got `{"ok": true}`. `scripts/chrome_bridge_check/check.mjs` repeats the
  first check, but it only proves what the environment it runs in can see. (The explanation
  given at the time, that Chrome had to be restarted, was wrong; see the correction above.)
- [x] Owner's Chrome check (in the owner's Default profile rather than a separate one; IDM's
  extension is also installed there, which didn't interfere with the right-click item):
  - With SDM closed, a right-click handoff started SDM (`sdm.exe --from-browser`, 5:42:05 PM)
    and opened "Add URL from the browser" filled in. That link was a web page, so the owner
    pressed Cancel: no history entry was added.
  - With SDM running, a handoff of python.org's `python-3.15.0-amd64.exe` was confirmed and
    completed: 45,383,680 bytes, the size the server announced, category Programs, in
    about 9 s. The file was not opened or run.
  - The first two tries said "host not found"; the try that worked used a Chrome that Claude
    had started from its sandboxed shell (to switch logging on), which could see the
    sandboxed registration. The owner's own Chrome only worked after the owner registered the
    host themselves (M8, 2026-10-20).

## M8: Browser handoff integrated with the download engine (done)

Done on branch `m8/browser-integration` (ADR-0015, spec FEAT-007):

- M8a (`c140cbf`): message version 2; the browser's Referer rules on every request, redirect
  hop, split part and resume; the browser's file name as a fallback; history schema version 5;
  https-to-http redirects refused for every download.
- M8b: the extension's opt-in capture (toolbar panel, optional `downloads` permission, minimum
  size, hand-back to Chrome without loops), right-click on video and audio, and the dialog
  showing what the browser knew.

Checked on 2026-10-19: 570 Python tests and 36 extension tests pass; ruff is clean. In a
throwaway headless Chrome, the new extension loaded, and a full version 2 message (referrer,
name, size, `source: capture`) went through the host to a throwaway SDM: `{"ok": true}`.

Fix after the owner's first capture test (`63ec0bf`, extension 0.2.1): with extension 0.2.0,
one click made Chrome's Save As appear again and again. Capture ran at `onCreated` (after Save
As), SDM's handoff failed ("host not found", see the M7 correction), and the download handed
back to Chrome was captured again because Chrome hadn't marked it with `byExtensionId`. Capture
now runs in `onDeterminingFilename`, before Save As; a handed-back address is left alone for
60 s; the toolbar panel shows the last problem.

Acceptance, met on 2026-10-20 in the owner's own Chrome (Default profile, capture on, the host
registered by the owner from their own PowerShell):

- [x] A normal left-click on python.org's "Windows embeddable package (64-bit)" opened SDM's
  "Captured from Chrome" dialog. SDM saved `python-3.14.7-embed-amd64 (5).zip`, 12,673,227
  bytes, completed; its history (schema version 5, the owner's real history, entry #1) keeps
  the browser's name `python-3.14.7-embed-amd64.zip` and the page `www.python.org`. The
  SHA-256 matches python.org's published value (checked in the owner's own terminal).
- [x] Hand-back: while the host couldn't be found, the panel said why and Chrome downloaded the
  file itself, showing Save As once (extension 0.2.1).
- [x] "Ask where to save each file" is on in the owner's Chrome. With 0.2.0, Chrome's Save As
  appeared before capture; 0.2.1 captures before it.
- Not checked separately: turning capture off again (covered by `popup.test.js`).

Note: the owner's real SDM history started with this download. The histories of the M2-M7
demos were written from Claude's sandboxed shell and are not in the owner's
`%LOCALAPPDATA%\SDM` (their downloaded files in Downloads are real).

## M9: Interface, settings, notifications and usability (done)

Done on branch `m9/usability` (ADR-0016, spec FEAT-008):

- M9a (`d6a5e57`): the shared speed limit, connections per download, SHA-256 checks (history
  schema version 6), SDM's saved preferences, and signals for notifications.
- M9b: the Settings dialog, the SHA-256 box in Add URL, the tray icon (optional close-to-tray),
  Windows notifications, the list's right-click menu, Show in folder (no Open), Copy address,
  Verify checksum, total speed in the status bar, remembered window layout and last folder.

Checked on 2026-10-20: 628 Python tests and 38 extension tests pass; ruff is clean. In tests a
3 MiB download split over several connections was held to 1 MiB/s (about 3 s). Screenshots of
the window, the menu and the Settings tabs (drawn off-screen with throwaway data) look right.

Acceptance, met on 2026-10-20 in the owner's own SDM (started from their own PowerShell):

- [x] With Settings > Connections at 1024 KB/s, python.org's `python-3.14.7-embed-amd64.zip`
  (12.1 MB) downloaded at about 1.0 MB/s and took about 12 s (owner's report). Entered with its
  published SHA-256, it ended "Completed · verified"; the saved `python-3.14.7-embed-amd64
  (6).zip` (12,673,227 bytes) matches python.org's SHA-256 on disk.
- [x] The Windows notification "Download complete and verified" appeared (owner's report).
- [x] Show in folder opened File Explorer with the file selected, without opening it.

Found in the demo and fixed: the status bar was empty. Qt replaces a status *message* with the
empty hint of any toolbar button or menu item the mouse passes over; the status now lives in a
permanent label (`test_the_status_line_survives_hovering_over_buttons`).

## M10: Security, performance, regression testing and Windows packaging (done)

On branch `m10/hardening` (ADR-0017):

- M10a: NAT64/6to4 addresses checked as their IPv4 address; the browser pipe refuses remote
  clients; seeded fuzz tests of every parser of untrusted data, which found and fixed five
  bugs; a rotating, redacted log file; a crash safety net; Help > Open log folder and About;
  `pip-audit`: no known vulnerabilities.
- M10b: performance measurements ([research/performance-m10.md](research/performance-m10.md)),
  which found that pre-sizing a split download's file wrote the whole file as zeros on the
  event loop (fixed with `set_file_size`); `scripts/check_all.py` runs every check;
  five full runs in a row passed (670 tests each, 2026-10-20): no flaky tests found.
- M10c: PyInstaller build (`dist\SDM`: SDM.exe, sdm-bridge-host.exe, licence notices) and a
  per-user Inno Setup installer script; Help > Set up / Remove Chrome integration for the
  installed app (ADR-0018). Smoke test of the build with throwaway data: the packaged host
  refused a bad message, SDM.exe started and logged version 0.1.0, the host handed a link
  to it, and with SDM closed the host started SDM.exe itself.

Acceptance, met on 2026-10-20 on the owner's PC:

- [x] The owner installed Inno Setup 6 and built `dist\SDM-Setup-0.1.0.exe` (30.2 MB) in their
  own PowerShell (2026-10-20; Claude's sandbox can't see the Inno Setup install).
  `build_release.py` now also finds Inno Setup through its uninstall registry entry, and has
  `--skip-build` (reuse `dist\SDM`) and `--iscc PATH`.
- [x] Installed per user into `%LOCALAPPDATA%\Programs\SDM` without
  administrator rights. Started from the Start menu: the history was there; Help > About
  showed SDM 0.1.0; python.org's embeddable zip with its SHA-256 ended "Completed · verified"
  (`(7).zip`).
- [x] Help > Set up Chrome integration registered the installed `sdm-bridge-host.exe`. The
  first capture failed ("SDM couldn't take the link"; Chrome kept the file, once): that SDM
  was running as administrator, and Windows refused Chrome's normal-level helper ("Access is
  denied", reproduced by running the installed host by hand). An SDM started normally (by the
  helper) accepted the link, and a normal left-click on python.org's zip then opened the
  installed SDM's "Captured from Chrome: python-3.14.7-embed-amd64.zip · 12.1 MB ·
  application/zip · from a page on www.python.org" dialog. SDM now warns at startup when it
  runs as administrator, and the host logs to `bridge-host.log` (`fa02d46`).
- [x] Uninstalled from Settings > Apps: the Start-menu entry and the Chrome registration were
  removed (`reg query` found no key); the history (`%LOCALAPPDATA%\SDM\sdm.db`) was kept.
- Note: the installer the owner tested (built before `fa02d46`) doesn't include the
  administrator warning or the host log yet; rebuild with
  `uv run python scripts/build_release.py --installer` to get them.

## M11: Open-source release on GitHub

Approved by the owner on 2026-10-20 (after M10): publish SDM as open source on their own
GitHub repository under the Apache License 2.0, with a UI/UX update (dark mode and a modern
look, progress bars and a details panel, a first-run setup assistant), an extension for
Chrome, Edge, Brave and Firefox (free Edge and Firefox stores plus GitHub zips), automated
GitHub releases, version 1.0.0, and the commit author email rewritten to the owner's GitHub
noreply address before the first push (owner to confirm right before).

- M11a: `LICENSE` (the official Apache-2.0 text, SHA-256 `cfc7749b...3d30`) and `NOTICE`;
  version 1.0.0 with licence metadata in `pyproject.toml` (the "do not upload" marker is
  gone); a public README, `CONTRIBUTING.md` and `SECURITY.md`; personal paths and the owner's
  extension ID replaced by neutral examples; "personal use" wording updated (About box,
  `CLAUDE.md`, a historical note on the brief).
- M11b (`c2c6e21` and this commit): light/dark themes following Windows, progress bars, a
  details panel, and a welcome assistant (folder, appearance, browsers). A test found that
  changing the theme with the assistant open crashed Qt; the style is now set only once.
- M11c: Edge, Brave and Firefox besides Chrome (ADR-0019): a fixed Chromium extension ID,
  per-browser registration with no typing, Firefox's own manifest, host arguments and
  capture path, `scripts/build_extensions.py` (Chromium, Edge store and Firefox zips), and
  the uninstaller cleaning up every browser. Checked: a throwaway headless Chrome and Edge
  each loaded the extension with the fixed ID and reached SDM's helper. Brave and Firefox
  aren't installed here: their parts are tested with fakes only.
- M11d: GitHub Actions: `checks.yml` (lint, format, Python tests on 3.12 and
  3.14, extension tests, on every push and pull request) and `release.yml` (a `v*` tag must
  match SDM's version; it builds the installer and the extension zips and publishes the
  installer, a portable zip and the Chromium zip with SHA-256 checksums; Edge and Firefox use
  their stores, ADR-0019). Actions are pinned to commit SHAs (checkout v7.0.1, setup-node
  v7.1.0, setup-uv v10.3.2). Checked locally on 2026-10-25: both workflows parse; the checks
  pass on Python 3.12 (scratch venv) and 3.14 (704 tests); `build_release.py --installer` and
  `build_extensions.py` built 1.0.0; the collect step ran in Windows PowerShell 5.1 (GitHub
  uses PowerShell 7). Not checked: the workflows on GitHub itself. Left: the repository address,
  the email rewrite (owner confirms first), the first push and release, and the owner's install
  test from the release.
- 1.0.0 was released on 2026-10-25 from github.com/Conditions-tech/SDM (history rewritten
  first so it shows only the owner's GitHub name). The owner's first try found that a click on
  a download still opened Chrome's Save As, since capture was off until switched on; at their
  request 1.0.1 turns capture on from installation (ADR-0015, amended).
- Installing 1.0.1 over 1.0.0 left `sdm-1.0.0.dist-info` beside `sdm-1.0.1.dist-info`, so
  About said 1.0.0 (owner's report). 1.0.2: the installer clears `{app}\_internal` first;
  tested with a throwaway Inno Setup installer over a fake old install.

**M11 marked done on 2026-10-25 at the owner's request.** Evidence:

- [x] Public repository github.com/Conditions-tech/SDM under Apache-2.0; every commit and tag by
  `Conditions-tech` with its GitHub noreply address; no personal name, email or path in any
  file or commit message (checked over the whole history before the push).
- [x] GitHub Actions on GitHub: Checks passed on Python 3.12 and 3.14 and for the extension;
  Release published 1.0.0, 1.0.1 and 1.0.2 (installer, portable zip, Chromium zip, SHA-256
  sums).
- [x] Owner: installed 1.0.0 and 1.0.1 from the releases (About box; Windows Apps listing),
  with earlier downloads kept. Their reports led to 1.0.1 (capture on from installation) and
  1.0.2 (About version after an update).
- [x] Headless Chrome and Edge loaded the extension with the fixed ID and reached SDM's
  helper; Chrome again with 1.0.1's permissions.
- [ ] **Open:** the owner's upgrade to 1.0.2 (About shows 1.0.2), and a click on a download in
  Chrome and in Edge opening SDM's dialog with 1.0.1 or later. To record when the owner runs it.
- [ ] **Open:** Brave and Firefox on a real PC; Edge Add-ons and Firefox Add-ons listings (the
  owner's submissions; their IDs then go into `browsers.py` and `sdm.core.links`).

## M12: Media converter and optional video-site add-on (in progress)

Approved by the owner on 2026-10-25 (option B), to start after M11d on branch `m12/media`.
Detailed plan approved 2026-10-25: the user installs ffmpeg and yt-dlp (SDM finds them);
yt-dlp does the video downloading; M12a converter, M12b video add-on, then release 1.1.0.

- M12a (done): ADR-0020; `sdm.media.ffmpeg`, the Convert window, Settings > Media, Convert… on
  finished downloads; 17 new tests with a fake ffmpeg. Left: the owner's check with the real
  ffmpeg.
- M12b (next): the optional video-page add-on with yt-dlp.

- **Converter (core feature):** convert a local file with ffmpeg, for example video to MP3
  audio, or MKV/WEBM to MP4. ffmpeg runs as a separate program; SDM never runs downloaded files
  and converts only files the user picks.
- **Video-site downloads (optional add-on, off by default):** the user turns on yt-dlp
  themselves; SDM does not ship it. Choices: 720p, 1080p, 4K (2160p) or audio only (MP3/M4A).
  1080p and 4K arrive as separate video and audio streams that ffmpeg merges. SDM shows a
  notice that the user is responsible for each site's terms.
- **Rule change:** the brief's "respect website terms" rule gets a note that site-specific
  downloads happen only through the user-enabled add-on; DRM, paywalls, logins and access
  controls stay off limits (no DRM-protected content, no cookie or account extraction).
- **Before code:** check yt-dlp (Unlicense) and ffmpeg (LGPL/GPL builds) licences and
  Windows support, and record an ADR. URLs from the add-on still count as untrusted input.
- **Tests:** synthetic media files and a fake yt-dlp executable; never real video sites.
- **Known limit:** no GPU here, so 4K conversion runs on the CPU and will be slow.
