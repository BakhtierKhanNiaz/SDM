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
| Pause and resume | Tested | M4 | ADR-0011; `test_resume.py`, `test_window_resume.py`. Same as IDM in OBS-006: resumes with `Range`, treats a `200` as no resume support, and uses a 64-byte overlap when there are no version tags. IDM's resume against a `206` server not yet observed |
| Crash / restart recovery | Tested | M4 | Interrupted entries keep their partial file and resume with `Range` (`test_resume_after_a_crash`); quitting pauses downloads; a corrupted history is set aside (M3) |
| Parallel segmented downloads | Investigated (partial) | M5 | OBS-001, 002, 004, 006: extra `Range` connections even without `Accept-Ranges`, dropped when the server answers `200` |
| Download queues | Not investigated | M6 | IDM's error text in OBS-006 mentions a queue that retries from the start (not tested) |
| Scheduled downloads | Not investigated | M6 | |
| Categories | Investigated (partial) | M6 | Documents (.pdf), Compressed (.zip), General (.bin), each with a save folder (OBS-001, 002, 005) |
| Browser-to-desktop handoff (explicit) | Not investigated | M7–M8 | |
| Automatic browser download capture (with consent) | Not investigated | M8 | |
| Speed limiter | Not investigated | M9 | |
| Connection limits | Not investigated | M9 | |
| Integrity verification (checksums) | Not investigated | M9 | |
| Settings dialog | Not investigated | M9 | |
| Notifications | Not investigated | M9 | |
| Windows installer / packaging | Not investigated | M10 | |

Target milestones are a first guess from the roadmap. They can move once features are
investigated.
