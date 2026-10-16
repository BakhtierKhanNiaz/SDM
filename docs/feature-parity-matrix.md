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

SDM's own implementation can reach *Tested* before IDM has been observed (as in M2), so the
notes say whether IDM was observed. A feature is never *Verified* without that comparison.

| Feature | Status | Target milestone | Evidence / notes |
|---|---|---|---|
| Download a file from a URL | Tested | M2 | FEAT-001; `tests/integration/test_http_download.py`; real-world download with checksum match (roadmap). IDM not yet observed |
| Filename detection and sanitization | Tested | M2 | ADR-0008; `tests/unit/test_filenames.py`, hostile-name security tests |
| Duplicate-filename policy | Tested | M2 | `name (n).ext`, never overwrite (ADR-0008). IDM's behavior unknown |
| Redirect handling | Tested | M2 | Manual, ≤ 10 hops, each re-checked (ADR-0007) |
| Timeouts and retry policy | Tested | M2 | 15 s connect / 30 s idle; 3 attempts; Retry-After honoured |
| Safe destinations (SSRF protection) | Tested | M2 | SDM-specific safety feature (ADR-0007); IDM comparison not applicable |
| Progress, speed and time remaining | Not investigated | M3 | |
| Cancel a download | Not investigated | M3 | |
| Download history | Not investigated | M3 | |
| Pause and resume | Not investigated | M4 | |
| Crash / restart recovery | Not investigated | M4 | |
| Parallel segmented downloads | Not investigated | M5 | |
| Download queues | Not investigated | M6 | |
| Scheduled downloads | Not investigated | M6 | |
| Categories | Not investigated | M6 | |
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
