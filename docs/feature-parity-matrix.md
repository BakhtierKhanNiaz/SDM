# Feature-parity matrix

Tracks each IDM-like feature from research through verification. Update it at the end of
every milestone. A status changes only when there is evidence (an observation entry, a spec,
code, or a passing test) to point to.

**Status values**, in order: Not investigated → Investigated → Specified → Implemented →
Tested → Verified. A feature can also be *Blocked / unsupported* (with a reason).

- *Investigated*: IDM's behavior is recorded in
  [behavior-observations.md](research/behavior-observations.md).
- *Specified*: requirements are in
  [feature-specifications.md](requirements/feature-specifications.md).
- *Verified*: SDM has been compared against the spec and the observed reference behavior.

SDM's own implementation can reach *Tested* before IDM has been observed, so the notes say
whether IDM was observed. A feature is never *Verified* without that comparison.
*Investigated (partial)* means some IDM behavior was seen in passing (mostly in the M2
session), not that the feature was studied in full.

| Feature | Status | Target milestone | Evidence / notes |
|---|---|---|---|
| Download a file from a URL | Verified | M2 | FEAT-001; `tests/integration/test_http_download.py`; real-world download (roadmap). Byte-identical to IDM's files (SHA-256) in OBS-001, 002, 004, 005. IDM also opens extra `Range` connections (an M5 topic) |
| Filename detection | Verified | M2 | Same names as IDM from `Content-Disposition` (OBS-001) and from the final URL after a redirect (OBS-004). ADR-0008 |
| Filename sanitization | Tested | M2 | `tests/unit/test_filenames.py`, hostile-name security tests. IDM not observed (SDM safety feature) |
| Duplicate-filename policy | Verified | M2 | OBS-002: IDM asks first (numbered `name_2.ext`, overwrite, or show/resume). SDM never overwrites and numbers `name (1).ext` without asking (ADR-0008). Difference explained: no download list until M3 |
| Redirect handling | Verified | M2 | OBS-004: both follow the redirect and name the file after the final URL. SDM re-checks each hop (ADR-0007) |
| HTTP errors (4xx) | Verified | M2 | OBS-003: neither retries a 404. SDM now says "not found" for 404/410 (`test_missing_file_fails_without_retrying`) |
| Unknown size (no `Content-Length`) | Verified | M2 | OBS-005: both save the whole file and warn that completeness can't be confirmed (`test_unknown_size`, `test_warns_only_when_completeness_cant_be_confirmed`). IDM's live progress for this case not observed (M3) |
| Timeouts and retry policy | Tested | M2 | 15 s connect / 30 s idle; 3 attempts; Retry-After honoured. IDM partly observed (OBS-003, OBS-006), but its automatic retry count wasn't established, so not Verified |
| Safe destinations (SSRF protection) | Tested | M2 | SDM-specific safety feature (ADR-0007); IDM comparison not applicable |
| Progress, speed and time remaining | Tested | M3 | FEAT-002; `TransferMeter` (3 s average), `test_live_progress_and_speed_reach_the_table`. IDM: OBS-005 (no size for unknown-size files), OBS-006 (stopped entry kept 50.00%). IDM's live display not observed (re-run R1), so not Verified |
| Cancel a download | Tested | M3 | FEAT-002; running and waiting downloads, and on quit (`test_cancel_then_remove_from_the_window`, `test_closing_with_downloads_running_asks_first`). IDM not observed |
| Download history | Tested | M3 | SQLite history survives restarts and keeps failed entries with their message (like IDM, OBS-003, OBS-006); warns about a URL downloaded before (OBS-002). ADR-0010 |
| Pause and resume | Tested | M4 | ADR-0011; `test_resume.py`, `test_window_resume.py`; real-world pause, restart and resume on python.org (roadmap). Same as IDM in OBS-006: resumes with `Range`, treats a `200` as no resume support, and uses a 64-byte overlap when there are no version tags. IDM's resume against a `206` server not yet observed |
| Crash / restart recovery | Tested | M4 | Interrupted entries keep their partial file and resume with `Range` (`test_resume_after_a_crash`); quitting pauses downloads; a corrupted history is set aside (M3) |
| Parallel segmented downloads | Tested | M5 | ADR-0012; `test_segmented.py`, `test_window_segmented.py`; real-world 8-connection download from python.org matched its SHA-256 (roadmap). IDM (OBS-001, OBS-004): 8 connections, extras at the final URL, dropped on `200`: SDM does the same, but splits only with version tags and parts of at least 1 MiB. Dynamic splitting halves the biggest part, the pattern OBS-001 suggests |
| Download queues | Tested | M6 | ADR-0013; order, limit 1-8, Start now, automatic retries after ~1/5/15 min (`test_queue.py`). IDM: OBS-006's message offers a queue that retries until success; its queue screens not observed |
| Scheduled downloads | Tested | M6 | Real-world: a python.org download waited for its window and started 1.7 s after it opened (roadmap). Start/stop times and days, overnight windows; only starts and pauses (`test_queue_planner.py`, `test_queue.py`). IDM's scheduler not observed |
| Categories | Tested | M6 | Same categories IDM showed (OBS-001, 002, 005) plus Music, Video, Programs; labels by default, IDM-style subfolders as a setting (off) |
| Browser-to-desktop handoff (explicit) | Tested | M7 | ADR-0014, FEAT-006: right-click "Download with SDM" on links opens Add URL filled in; starts SDM if needed. Owner's Chrome check passed (roadmap). IDM's browser integration not observed |
| Automatic browser download capture (with consent) | Tested | M8 | ADR-0015, FEAT-007: on from installation since 1.0.1 (owner's choice; the toolbar switch turns it off; was opt-in in M8), minimum size, hand-back to Chrome. Referer and the browser's name forwarded; no cookies. Owner's check passed: a captured python.org download matched its SHA-256 (roadmap). IDM's capture not observed |
| Speed limiter | Tested | M9 | ADR-0016: one limit shared by all downloads, applied at once. Owner's demo: 1 MB/s held on python.org (roadmap). IDM's limiter not observed |
| Connection limits | Tested | M9 | Connections per download 1-8 (Settings); downloads at once 1-8 (Scheduler, M6). IDM's per-site exceptions (OBS-006 text) not observed |
| Integrity verification (checksums) | Tested | M9 | SHA-256 in Add URL or later; mismatched files kept and flagged; owner's demo verified a python.org download (roadmap). Size-unconfirmed warning since M2 (OBS-005) |
| Settings dialog | Tested | M9 | General, Connections, Notifications tabs; queue settings in Scheduler. IDM's Options not observed |
| Notifications | Tested | M9 | Windows notifications (not dialogs, unlike IDM's completion dialog, OBS-001); optional close-to-tray |
| Windows installer / packaging | Tested | M10 | ADR-0018: PyInstaller build and a per-user Inno Setup installer; the owner installed, used (verified download, Chrome capture) and uninstalled it (roadmap). Not code-signed ($0). Since 1.0.2 an update replaces the old program files (`test_an_update_replaces_the_old_program_files`) |
| Browsers: Chrome, Edge, Brave, Firefox | Tested | M11 | ADR-0019: fixed Chromium ID, per-browser registration from the welcome assistant, Firefox package (`test_browsers.py`, `background.firefox.test.js`). Headless Chrome and Edge reached SDM's helper; Brave and Firefox tested with fakes only (not installed). IDM's browser support not observed |
| Themes, progress bars, details panel | Tested | M11 | ADR-0019: light/dark following Windows, WCAG AA contrast checked (`test_window_m11.py`). IDM's look not compared (SDM's own design) |
| First-run welcome assistant | Tested | M11 | ADR-0019: folder, appearance, browsers; remembered when cancelled (`test_packaging.py`). The owner's run of it not yet recorded |
| Convert video/audio (ffmpeg) | Tested | M12 | ADR-0020, FEAT-009: MP3, M4A, MP4 next to the source, with progress and Cancel; tested with a fake ffmpeg (`test_convert.py`) and the real ffmpeg 9.0.2 (`test_convert_real_ffmpeg.py`, checked with ffprobe). The owner's check in their SDM is still to do. IDM's converter not observed |
| Video-page downloads (yt-dlp, optional) | Tested | M12 | ADR-0020, FEAT-010: off by default; 720p/1080p/4K/MP3/M4A; pause, resume, cancel in the normal list; tested with a fake yt-dlp (`test_video.py`) and the real yt-dlp 2026.10.21 against a local test server (`test_video_real_ytdlp.py`, ffprobe). The owner's check on a real video page is still to do. IDM's video features not observed |
| Public releases (GitHub Actions) | Tested | M11 | `.github/workflows`: checks on every push; a version tag publishes installer, portable zip, Chromium zip and SHA-256 sums (1.0.0-1.0.2 published). No in-app update check |

Target milestones are a first guess from the roadmap. They can move once features are
investigated.
