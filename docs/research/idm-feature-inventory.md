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

None of these has been investigated yet. They come from the project goals and still need
checking against IDM.

| Feature | Source | Observation refs | Notes |
|---|---|---|---|
| Add a download from a URL | Goal | — | |
| Progress, speed, time remaining | Goal | — | |
| Pause / resume / cancel / retry | Goal | — | |
| Download history and queues | Goal | — | |
| Segmented (multi-connection) downloads | Goal | — | |
| Recovery after restart | Goal | — | |
| Browser download capture and handoff | Goal | — | |
| Scheduler | Goal | — | |
| Categories | Goal | — | |
| Speed limiter | Goal | — | |
| Connection limits | Goal | — | |
| Filename handling and duplicates | Goal | — | |
| Integrity verification | Goal | — | |
| Settings and notifications | Goal | — | |
