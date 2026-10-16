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

| Feature | Status | Target milestone | Evidence / notes |
|---|---|---|---|
| Download a file from a URL | Not investigated | M2 | |
| Filename detection and sanitization | Not investigated | M2 | Windows path limit is ~260 chars (long paths disabled) |
| Duplicate-filename policy | Not investigated | M2 | |
| Redirect handling | Not investigated | M2 | |
| Timeouts and retry policy | Not investigated | M2 | |
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
