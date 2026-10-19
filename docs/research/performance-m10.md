# Performance measurements (M10b)

Measured on 2026-10-20 on the owner's PC (Intel i3-8100, 8 GB RAM, Windows 10; files written to
C:, a SATA SSD "WALTON WS5256 256GB"; D: is a 1 TB hard disk). Everything is local: a test
server in a separate process serves a deterministic file over 127.0.0.1. Reproduce with:

```powershell
uv run python scripts/perf/measure.py --size-mib 1024
```

These are observations on one PC, not guarantees. Disk state matters a lot: the same
measurement varied by 2-4x within an hour, after several GB had been written.

## A bug found by measuring

The first run showed 8 connections much slower than 1 (132 against 286 MiB/s), although the
test server alone delivered 509 MiB/s over 8 plain connections. Profiling found the cause:
Python's `truncate()` grows a file on Windows by **writing zeros**, so pre-sizing the partial
file of a split download wrote the whole file (3.6-5 s for 512 MiB) before the parts could
start, on the event loop thread that every connection shares, and undid the sparse flag.
Fixed with `set_file_size` (`SetFileInformationByHandle`, which writes nothing): pre-sizing
512 MiB now takes 0.000 s and the file stays sparse
(`test_presizing_a_part_file_writes_nothing`).

## Results

### Downloads of 1024 MiB from a local server

| Run | Connections | Time | Speed | CPU time | SHA-256 |
|---|---|---|---|---|---|
| Before the fix | 1 | 3.6 s | 286 MiB/s | 2.4 s | 2.9 s (349 MiB/s) |
| Before the fix | 8 | 7.7 s | 132 MiB/s | 3.5 s | 3.0 s (338 MiB/s) |
| After the fix | 1 | 3.8 s | 266 MiB/s | 2.8 s | 4.2 s (246 MiB/s) |
| After the fix | 8 | 12.3 s | 83 MiB/s | 2.6 s | 4.4 s (231 MiB/s) |

- **Memory:** the downloading process peaked at **46 MiB** for a 1 GiB file (data streams
  to disk; nothing holds the file in memory).
- **8 connections on a local server are disk-bound on this PC:** after the fix, the 8-connection
  run used only 2.6 s of CPU in 12.3 s. Most of the wait is the disk: a disk-only test of 8
  interleaved write streams into a sparse file reached 57-114 MiB/s, and even one sequential
  stream fell to 55 MiB/s by then, as the SSD's fast write cache filled. The SHA-256 speed
  dropping from 349 to 246 MiB/s between runs points the same way.
- **Where splitting helps:** servers that limit speed per connection (M5: 4 connections took
  1.02 s against 4.02 s for one, `test_split_download_beats_a_per_connection_speed_limit`).
  On a fast local server one connection is already as fast as the disk.
- Not changed: writing each part in larger pieces looked faster in the disk-only test
  (114 MiB/s for 1 MiB pieces against 57 for 64 KiB), but buffering part data changes what
  the saved parts map may claim (ADR-0012's resume rules). Left for later, with care.

### The window

| Measurement | Run 1 | Run 2 |
|---|---|---|
| Open with 10,000 history entries | 0.76 s | 2.28 s |
| Scroll through all 10,000 entries (770 pages) | 10 ms per page | 9 ms per page |
| 8 downloads of 64 MiB at once | 4.5 s | 5.7 s |
| ...a 10 ms timer's lateness: median / 99th percentile / worst | 0 / 18 / 137 ms | 0 / 19 / 56 ms |

The window stays responsive with 8 downloads running: half of the timer ticks are on time and
99% are less than 20 ms late (a frame at 60 Hz is 17 ms). The worst single delay (56-137 ms)
is a brief hitch, not a freeze.
