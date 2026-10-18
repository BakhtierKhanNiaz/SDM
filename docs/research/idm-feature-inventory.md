# IDM feature inventory

The list of IDM features to investigate, and where knowledge about each came from. This is
the starting point for Stage A (Observe).

**Reference install:** Internet Download Manager 6.42 build 22 (file version of `IDMan.exe`,
checked 2026-10-17).

## Rules

- Black-box only: what the UI shows, what goes over the network, and public documentation.
  No decompiling, disassembling or copying of IDM code or assets.
- Each entry names its **source**: *Observed* (we did it and saw it, with an entry in
  [behavior-observations.md](behavior-observations.md)), *Documented* (public IDM docs, with
  a link), or *Goal* (from the project brief, not yet checked against IDM).

## Inventory

The M2 comparison (2026-10-18) gave the first observations. *Observed (partial)* means only
what those six scenarios happened to show.

| Feature | Source | Observation refs | Notes |
|---|---|---|---|
| Add a download from a URL | Observed | OBS-001 to OBS-006 | Add URL → Download File Info (URL, category, save path, size) → Start Download → "Download complete" dialog |
| Progress, speed, time remaining | Observed (partial) | OBS-005, OBS-006 | Live progress not seen; unknown sizes show no size; a stopped entry keeps its last %, time left and rate |
| Pause / resume / cancel / retry | Observed (partial) | OBS-003, OBS-006 | Resume via `Range`; a `200` reply is reported as "does not support 'resume'". No retry after a 404. Automatic retry count unknown |
| Download history and queues | Observed (partial) | OBS-003, OBS-006 | The list keeps failed entries ("Error", "Not Found", 50.00%) with a Last Try Date. Queues not tested |
| Segmented (multi-connection) downloads | Observed (network only) | OBS-001, 002, 004, 006 | Extra `Range` connections even without `Accept-Ranges` |
| Recovery after restart | Goal | — | |
| Browser download capture and handoff | Goal | — | |
| Scheduler | Goal | — | |
| Categories | Observed (partial) | OBS-001, 002, 005 | Category chosen by file type; per-category save folder and a "Remember this path" option |
| Speed limiter | Goal | — | |
| Connection limits | Goal | — | OBS-006's error text points to per-site connection exceptions in Options (not tested) |
| Filename handling and duplicates | Observed | OBS-001, 002, 004 | `Content-Disposition` name; final URL after a redirect; duplicate dialog with numbered `name_2.ext` |
| Integrity verification | Observed (partial) | OBS-005 | Warns when completeness can't be confirmed (size unknown) |
| Settings and notifications | Goal | — | Completion dialog with "Don't show this dialog again" seen (OBS-001) |
