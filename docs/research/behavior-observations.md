# IDM behavior observations

Facts seen in controlled tests of IDM. Hypotheses go in their own labelled field and are
never mixed with what was seen.

Every finding carries one of these labels:

- **Observed**: seen on screen (screenshot) or reported by the tester while operating IDM.
- **Verified**: checked independently from the scenario server's request log, the saved files
  (size, SHA-256, timestamps) or the Windows event log.
- **Inferred**: a hypothesis that fits the evidence but was not tested. Never treat it as fact.
- **Not observed**: asked for, but no evidence exists.

## M2 comparison session (2026-10-18)

### Common setup

- **IDM:** 6.42 build 22 on Windows 10 Pro, operated by hand by the project owner through
  **Add URL**. Claude analysed the screenshots, the request log and the saved files. No IDM
  files, memory or data folders were inspected.
- **Server:** `scripts/idm_scenarios/server.py` on `http://127.0.0.1:8765`, logging to
  `logs/idm-requests.jsonl`. It ignores `Range`, always answers `200` with the whole body,
  never sends `Accept-Ranges`, `ETag` or `Last-Modified`, and closes the connection after
  every response.
- **Download folder:** `D:\idm download for projects\` (shown in every completion dialog and
  confirmed on disk).
- **Evidence:** screenshots in `logs/idm-evidence/` and the request log. Both are git-ignored
  and exist only on the owner's computer; IDM screenshots are never committed.
- **Settings note (Observed):** from the duplicate download in Scenario 2 onwards, the
  "Remember this path for ... category" box was ticked in the Download File Info dialog
  (Compressed, then General). That may have stored `D:\idm download for projects\` as those
  categories' default folder. It wasn't changed back.

### How to read the request log

- The server writes a line when a request **ends**. `time` is the end time (local clock, no
  date), so the order of lines is the order in which requests finished, not started.
- `status: 0` means the client closed the connection before the server finished. For those
  lines, `bytes_sent` is always `0`, whatever was really sent before the hang-up (a limit of
  the logger). For other lines, `bytes_sent` counts bytes handed to Windows, not bytes the
  client read.
- Who sent what (Verified, by User-Agent):

| Log lines | Client | What |
|---|---|---|
| 1–3 | `WindowsPowerShell/5.1` | Server health checks, 2026-10-17 |
| 4–10, 25 | `SDM-route-check` | Claude's route checks after each server restart (2026-10-18 12:59 and 20:00) |
| 11–24, 26–45 | `Mozilla/5.0 (Windows NT 6.1; Trident/7.0; rv:11.0) like Gecko` | IDM |

- **Server downtime (Verified, Windows event log):** Windows started at 12:02, was powered
  off at 15:55 and started again at 18:59. The server ran from about 12:59 to 15:55 and from
  20:00 onwards. IDM attempts made while it was down never reached it and are not scenario
  evidence: the `dl` entry (Last Try 12:47:55) and the first `missing.zip` (19:53:22) in IDM's
  list.
- **Clock (Verified):** Windows corrected its clock by about 52 minutes at 14:08, between
  Scenarios 2 and 3. Times within each scenario are consistent.
- **Observed, all scenarios:** the "Last Try Date" in IDM's list is 2–3 s earlier than the
  server's end time for the same burst (for example 13:03:12 vs 13:03:15). Cause unknown.

### Evidence by scenario

| # | Screenshots (`logs/idm-evidence/`) | Log lines | Saved file (SHA-256 vs `EXPECTED`) | Evidence status |
|---|---|---|---|---|
| 1 | `s1-dialog.png`, `s1-dialog-download-complete.png` | 11–18 | `Report 2026.pdf`, 1,048,576 bytes, matches | Complete |
| 2 | `s2-dialog.png`, `s2-dialog-download-completed.png`, `s2-duplicate-download-link-dialog.png`, `s2-duplicate-download-dialog.png`, `s2-duplicate-dialog-download-completed.png` | 19–24 | `sample.zip` and `sample_2.zip`, 1,048,576 bytes each, both match | Complete |
| 3 | `s3-dialog-error.png`, `s3-final-status.png` | 26–27 | none (correct) | Complete |
| 4 | `s4-dialog.png`, `s4-dialog-download-completed.png` | 28–31 | `archive.zip`, 1,048,576 bytes, matches | Complete |
| 5 | `s5-dialog.png`, `s5-dialog-download-completed.mp4.png`; video `s5-dialog-download-capture..mp4` not inspected | 32–33 | `stream.bin`, 3,145,728 bytes, matches | **Partial:** progress display not observed |
| 6 | `s6-dialog.png`, `s6-first-error.png`, `s6-retry-status.png`, `s6-final-status.png` | 34–45 | none in the download folder | **Partial:** retry count and who started tries 2–3 unknown |

### OBS-001: Filename from Content-Disposition

- **Date / IDM version:** 2026-10-18 / 6.42 build 22
- **Setup:** `GET /dl?id=7` answers `200`, `Content-Type: application/pdf`,
  `Content-Disposition: attachment; filename="Report 2026.pdf"`, `Content-Length: 1048576`.
  The URL typed into IDM was `http://127.0.0.1:8765/dl?id=7.` (a trailing period, by mistake).
- **Steps:** 1. Add URL, paste the URL, OK. 2. Download File Info dialog appears. 3. Start
  Download. 4. Completion dialog, Close.
- **Observed result:**
  - *Observed:* Download File Info: URL shown with the trailing period; Category
    "Documents"; Save As `Downloads\Documents\Report 2026.pdf`; size "1.00 MB"; buttons
    Download Later, Start Download, Cancel. Completion dialog "Download complete": "Downloaded
    1.00 MB (1048576 Bytes)", saved as `D:\idm download for projects\Report 2026.pdf`, buttons
    Open, Open with..., Open folder, Close. How the folder changed from the one in the first
    dialog wasn't recorded.
  - *Verified:* IDM requested `/dl?id=7.`, with the period. The server ignores the query
    string, so the response was the same as for `/dl?id=7`. There were 8 GETs, all ending at
    13:03:15, and no HEAD. One had no `Range` (200, whole body sent). Seven had `Range`:
    `bytes=233600-1048575` (200, whole body sent), then `bytes=233600-`, `646927-`,
    `853591-`, `956923-`, `1008589-` and `1034422-`, all closed by IDM (status 0). Every
    request had `Accept-Encoding: identity` and `Accept: */*`, and none had `If-Range`. The
    saved file is 1,048,576 bytes with the expected SHA-256 (`1f0e3be0…e3712`). It was last
    written at 13:03:15 (the second the server finished) but created at 13:04:23, after the
    dialog screenshot was saved (13:04:07).
- **Evidence:** `s1-dialog.png`, `s1-dialog-download-complete.png`; log lines 11–18.
- **Hypotheses (not verified):**
  - IDM tried to split the file across extra connections with `Range` requests, although
    the server never advertised range support, and dropped them when the server answered
    `200` instead of `206`. Each new start point is half as far from the previous one as the
    one before (413,327 → 206,664 → 103,332 → 51,666 → 25,833 bytes), which looks like
    repeatedly splitting the last remaining part in two.
  - IDM starts downloading as soon as the URL is added, while the dialog is still open, and
    creates the file in the chosen folder only after Start Download. The file's write time
    is earlier than its creation time, which fits a copy that keeps the original write time.
- **Open questions:** Does IDM wait for Start Download before transferring a large or slow
  file? What name does it use with no `Content-Disposition` and no extension? The `dl` entry
  from the server-down attempt suggests the last URL segment, query dropped, but that attempt
  never reached the server.

### OBS-002: Same URL added twice

- **Date / IDM version:** 2026-10-18 / 6.42 build 22
- **Setup:** `GET /files/sample.zip` answers `200`, `application/zip`, 1,048,576 bytes, no
  `Content-Disposition`.
- **Steps:** 1. Add URL, Start Download, completion dialog, Close. 2. Add URL with the same
  URL. The "Duplicate download link" dialog appears; choose the numbered-name option, OK.
  3. Download File Info, Start Download, completion dialog, Close.
- **Observed result:**
  - *Observed:* First dialog: Category "Compressed", Save As `Downloads\Compressed\sample.zip`,
    "1.00 MB", a disabled Preview button. Saved as `...\sample.zip`. The duplicate dialog
    shows the URL, says the file is already in the download list, and offers three options
    (or Cancel to skip):
    1. "Add the duplicate with a numbered file name" (selected in the screenshot)
    2. "Add the duplicate and overwrite the existing file"
    3. "If existing file is complete, show download complete dialog; otherwise resume it."

    It also has a "Remember my selection and don't show this dialog again" box (not ticked),
    which mentions IDM Options → Downloads. Second Download File Info: Save As
    `D:\idm download for projects\sample_2.zip`, with the remember-path box for "Compressed"
    ticked. Saved as `...\sample_2.zip`, 1048576 Bytes.
  - *Verified:* two bursts of 3 GETs (ending 13:07:28 and 13:09:59) with the same shape: no
    `Range` (200); `bytes=1025215-1048575` (200, whole body sent); `bytes=1025215-` (200,
    whole body sent). `sample.zip` and `sample_2.zip` are both 1,048,576 bytes with the
    expected SHA-256 (`b4f2243e…4c281d`). `sample.zip` was not touched by the second download.
    The duplicate check didn't need the server. No request ended between 13:07:28 and
    13:09:59, and IDM's Last Try Date for `sample_2.zip` (13:09:56) is later than the moment the
    duplicate dialog's screenshot was saved (13:09:53).
- **Evidence:** the five `s2-*.png` files; log lines 19–24.
- **Hypotheses (not verified):** The duplicate check compares the URL with IDM's download
  list (the dialog's wording), not files on disk. Numbering looks like `name_N.ext` starting
  at 2, but that's one data point.
- **Open questions:** Is the numbered option the default, or was it selected before the
  screenshot? What does a third add produce? What happens if the file exists on disk but not
  in the list, or the same name comes from a different URL?

### OBS-003: 404 Not Found

- **Date / IDM version:** 2026-10-18 / 6.42 build 22
- **Setup:** `GET /missing.zip` answers `404 Not Found` (text body, 9 bytes). Before the
  retry, the server was restarted and checked at 20:00:41 (log line 25). An earlier attempt
  at 19:53 failed only because the server was down.
- **Steps:** Add URL; error message; OK; watch for about 30 s.
- **Observed result:**
  - *Observed:* a message box titled `missing_2.zip`: "The requested file doesn't exist."
    with "Details: HTTP/1.1 404 Not Found" and an OK button. IDM numbered the name because the
    failed `missing.zip` entry was already in its list; whether a duplicate dialog appeared
    wasn't recorded. The list shows `missing.zip` "Error" (19:53:22, server down) and
    `missing_2.zip` "Not Found" (20:05:27). The tester saw no retry in about 30 s.
  - *Verified:* 2 GETs for `/missing.zip`, both ending at 20:05:30, both 404, no `Range`.
    There are no more `/missing.zip` requests in the rest of the log (to 21:19:37, 74
    minutes). No file was written.
- **Evidence:** `s3-dialog-error.png`, `s3-final-status.png`; log lines 26–27.
- **Hypotheses (not verified):** The second request may be an immediate repeat, or a separate
  check-then-download step. The log can't tell which.
- **Open questions:** Why two requests? Does IDM retry other errors (403, 410, 5xx), and how
  often? This covers one 404 case only.

### OBS-004: 302 redirect

- **Date / IDM version:** 2026-10-18 / 6.42 build 22
- **Setup:** `GET /start` answers `302` with `Location: /files/archive.zip` (relative); the
  final URL answers `200`, `application/zip`, 1,048,576 bytes.
- **Steps:** Add URL `http://127.0.0.1:8765/start`; Start Download; completion dialog; Close.
- **Observed result:**
  - *Observed:* the Download File Info URL field shows the **final** URL
    `http://127.0.0.1:8765/files/archive.zip`, not `/start`. Category "Compressed", Save As
    `D:\idm download for projects\archive.zip`, "1.00 MB". The completion dialog's Address is
    also the final URL. Saved as `...\archive.zip`.
  - *Verified:* 4 GETs ending at 20:10:46: `/start` → 302 (once), then `/files/archive.zip`
    with no `Range` (200), `bytes=1025215-1048575` (200) and `bytes=1025215-` (200). The extra
    connections went straight to the final URL. The file is 1,048,576 bytes with the expected
    SHA-256 (`d077416d…57a0`).
- **Evidence:** `s4-dialog.png`, `s4-dialog-download-completed.png`; log lines 28–31.
- **Hypotheses (not verified):** IDM stores the final URL in place of the original, since the
  list and both dialogs show it.
- **Open questions:** Does IDM keep the original URL for re-downloading or resuming? What
  about chains of redirects, or a redirect to another host?

### OBS-005: Unknown size (no Content-Length)

- **Date / IDM version:** 2026-10-18 / 6.42 build 22
- **Setup:** `GET /stream.bin` answers `200`, `application/octet-stream`, no `Content-Length`
  and no chunked encoding, so only the connection closing marks the end. 3,145,728 bytes in
  about 6 s.
- **Steps:** Add URL; Start Download; completion dialog; Close. A screen recording was made
  too.
- **Observed result:**
  - *Observed:* Download File Info: Category "General", Save As
    `D:\idm download for projects\stream.bin`, and **no size** next to the icon (other dialogs
    show for example "1.00 MB" there). The completion dialog says "Download complete.
    Downloaded 3.00 MB (3145728 Bytes)." and warns: "The file may not have been downloaded
    completely because the file size is unknown." In the list, `stream.bin` is "Complete"
    with an empty Size column.
  - *Verified:* 2 GETs. One with `Range: bytes=0-` was closed by IDM at 20:14:26 (status 0).
    One with no `Range` ended at 20:14:32 after the whole 3,145,728 bytes. The saved file has
    the expected SHA-256 (`405a35ee…68156`). It was last written at 20:14:32 and created at
    20:14:50, after the dialog screenshot was saved (20:14:39).
  - *Not observed:* the progress, transfer rate and time left **during** the transfer.
    Timestamps show why (Verified): the transfer finished at 20:14:32, before the dialog
    screenshot was saved and before Start Download created the file. So there was no running
    download to watch. The video `s5-dialog-download-capture..mp4` was not inspected: the
    project has no video decoder and none was installed.
- **Evidence:** `s5-dialog.png`, `s5-dialog-download-completed.mp4.png`; log lines 32–33.
- **Hypotheses (not verified):** The `Range: bytes=0-` request checks whether the server
  supports resuming. As in OBS-001, IDM transfers while the dialog is still open.
- **Open questions:** How does IDM show progress and time left when the size is unknown?
  Re-run with a stream long enough (60 s or more) to still be running after Start Download.
  Does IDM give the same warning for a chunked response, which does mark its end?

### OBS-006: Connection cut halfway, every time

- **Date / IDM version:** 2026-10-18 / 6.42 build 22
- **Setup:** `GET /cut.bin` answers `200` with `Content-Length: 4194304`, sends 2,097,152
  bytes in about 1.6 s, then closes. It does this every time and ignores `Range`.
- **Steps (as recorded):** Add URL; Start Download; error message; OK. IDM list screenshots at
  21:15 and 21:22. Who started the second and third tries wasn't recorded.
- **Observed result:**
  - *Observed:* Download File Info: `cut.bin`, Category "General", "4.00 MB". An error
    message titled `cut.bin` begins: "The data transfer has been interrupted and the server
    does not support 'resume'." It adds that the file can only be downloaded from the
    beginning. It then suggests (paraphrased) trying to resume later, or putting the file
    alone in a queue (IDM then retries from the beginning until it succeeds), and setting one
    connection for this site in the Options → Connection exceptions. Details: "The server sent
    incorrect reply on restart command." In the list at 21:15 (`s6-retry-status.png`):
    `cut.bin`, 4.00 MB, 50.00%, Time left "1 sec", Transfer rate "0 Bytes/sec", Last Try
    20:26:19. At 21:22 (`s6-final-status.png`): 50.00%, Time left and rate empty, Last Try
    21:19:32. `s6-first-error.png` was saved at 21:20:09, so it may show the third try's error
    rather than the first.
  - *Verified:* 12 GETs in three identical bursts of four, ending 20:23:12–14, 20:26:22–24
    and 21:19:35–37:
    1. `Range: bytes=233600-4194303`, closed by IDM (status 0)
    2. `Range: bytes=233600-`, closed by IDM
    3. no `Range`: 200, all 2,097,152 bytes the server ever sends
    4. `Range: bytes=2097088-`, closed by IDM

    2,097,088 is 2,097,152 − 64: the resume request starts 64 bytes before the end of the
    data received. There were no requests between 20:26:24 and 21:19:35 (53 minutes), so IDM
    didn't retry by itself in that time. The "1 sec" and "0 Bytes/sec" at 21:15 were shown
    while the log shows no activity. No `cut.bin` or partial file is in the download
    folder. Where IDM keeps the 2 MiB it received wasn't checked: that would mean looking
    inside IDM's own data folders.
  - *Not observed:* how many tries IDM makes **automatically**, and with what delays.
- **Evidence:** the four `s6-*.png` files; log lines 34–45.
- **Hypotheses (not verified):**
  - IDM noticed the short body (50.00% is 2 of 4 MiB) and tried to resume with a `Range`
    request. The server's `200` instead of `206 Partial Content` is the "incorrect reply on
    restart command", so IDM gave up and reported that resuming isn't supported.
  - The 64-byte overlap may be used to check that the data already received still matches.
  - The 3-minute and 53-minute gaps between tries suggest they were started by hand, not by
    a retry timer.
- **Open questions:** Re-run while writing down every click, to count automatic retries and
  their delays. Does IDM keep the partial data and resume properly when the server answers
  `206`? What does the queue option do?

## IDM vs SDM

SDM results come from `uv run python scripts/idm_scenarios/run_sdm.py` on 2026-10-18 (engine
called directly with loopback allowed, after the changes in [Findings](#findings)). SDM sends
`User-Agent: SDM/0.1.0`, `Accept-Encoding: identity`, `Accept: */*`, and never `Range` or
HEAD.

| # | Behavior | IDM | SDM | Same? |
|---|---|---|---|---|
| 1 | Name from `Content-Disposition` | `Report 2026.pdf` (OBS-001) | `Report 2026.pdf`, hash matches | **Same** |
| 1 | Requests for a 1 MiB file | 8 GETs: 1 plain + 7 `Range` attempts, dropped on `200` | 1 GET | Different: extra connections are an M5 topic |
| 2 | Second download of the same URL | Asks first; options: numbered name, overwrite, show or resume the existing download. Numbered → `sample_2.zip` (OBS-002) | Never asks, never overwrites: `sample (1).zip` | Different, explained: SDM has no download list until M3; naming follows ADR-0008 |
| 3 | 404 | "The requested file doesn't exist." plus the status line; 2 requests; no retry in 74 min (OBS-003) | "The file was not found on the server (404 Not Found)."; 1 request; no retry | **Same outcome** (SDM's message used to say "refused") |
| 4 | 302 redirect | Final URL shown; named `archive.zip` (OBS-004) | Named `archive.zip`, after the final URL; 2 requests | **Same** |
| 5 | No `Content-Length` | Full 3,145,728 bytes; warns completeness can't be confirmed; no size in the dialog (OBS-005) | Full 3,145,728 bytes in 6.1 s; `sdm-get` now warns as well; progress shows "(size unknown)" | **Same outcome**; IDM's live progress display not observed |
| 6 | Connection cut halfway | Detects it (50.00%), tries a `Range` resume, gets `200`, stops with "does not support 'resume'"; entry kept at 50%; no automatic retry seen in 53 min (OBS-006) | Detects it; 3 attempts, each from byte 0 (1 s and 2 s waits, about 6 MiB thrown away); "The download was interrupted by a network error."; partial file deleted | Different, explained: SDM has no resume until M4 |

## Findings

### Fixed in this change (evidence-backed, with regression tests)

- **F1 (OBS-005): no warning when completeness can't be confirmed.** When only a closing
  connection marks the end of a download, a dropped connection looks exactly like a finished
  one. IDM warns about this; SDM said nothing. Now `DownloadResult.verified_complete` is
  `False` in that case and `sdm-get` prints a warning. Chunked responses count as complete,
  because aiohttp fails if the final chunk never arrives. Tests: `test_unknown_size`,
  `test_chunked_download_counts_as_complete`,
  `test_chunked_download_cut_before_the_last_chunk_fails`,
  `test_warns_only_when_completeness_cant_be_confirmed`.
- **F2 (OBS-003): misleading 404 message.** SDM called a missing file "refused". 404 and 410
  now say "The file was not found on the server (...)", and other 4xx errors still say
  "refused". Tests: `test_missing_file_fails_without_retrying`,
  `test_other_client_errors_are_refusals`.

### Gaps already planned (no code change now)

| Gap | Evidence | Milestone | Follow-up test to add then |
|---|---|---|---|
| Resume with `Range`: accept only `206` with a matching `Content-Range`, otherwise restart cleanly | OBS-006 | M4 | A server that ignores `Range` (`200`) must cause a restart, never a corrupted file; a `206` server must resume from the right byte |
| Keep partial data between retries instead of re-downloading from byte 0 | OBS-006 (SDM wastes about 6 MiB) | M4 | Count bytes requested per attempt |
| Extra connections, falling back safely when the server ignores `Range` | OBS-001, 002, 004, 006 | M5 | Server ignores `Range`: output must still match the SHA-256 |
| Warn when a URL is already in the download history | OBS-002 | M3 (history), M9 (prompt) | Same URL twice → warning, no overwrite |
| Categories by file type, each with its own folder | OBS-001, 002, 005 | M6 | — |
| Show how much arrived when a download is cut (IDM: 50.00%) | OBS-006 | M3 | Cut download → message includes "2.0 MB of 4.0 MB" |

### Proposals for the owner (not done)

- **P1:** improve the scenario server's log, recording each request's start time and the
  bytes really sent before a hang-up (status-0 lines hide this). Also add a slow stream (60 s
  or more) for the progress test. This changes `scripts/idm_scenarios/server.py` only.
- **P2:** re-run Scenario 5 with the slow stream to observe IDM's progress, rate and time
  left. Re-run Scenario 6 while writing down every click, to count automatic retries.
- **P3:** consider an option for SDM's User-Agent. IDM presents itself as Internet Explorer
  11; SDM identifies itself honestly as `SDM/0.1.0`. No server in these tests treated them
  differently, so there's no evidence for a change yet (M9).

### Missing evidence

- Scenario 5: IDM's progress, transfer rate and time left during an unknown-size download.
  **Not observed**, so not Verified.
- Scenario 6: the number and timing of IDM's automatic retries. **Not established**: the log
  shows three tries but not who started them.
- The screen recording `s5-dialog-download-capture..mp4` hasn't been reviewed.
- Where IDM keeps the partial data of `cut.bin`: not checked, by the black-box rule.

## How to record an observation

Copy this template, give it the next number, and fill in every field. Write "unknown" rather
than guessing.

```markdown
### OBS-001: <short title>

- **Date / IDM version:** 2026-MM-DD / 6.42 build 22
- **Setup:** settings changed from default, network conditions, test server and file used
- **Steps:** numbered user actions
- **Observed result:** exactly what appeared or happened (UI text, files written, timing),
  labelled Observed / Verified / Not observed
- **Evidence:** screenshot path under logs/idm-evidence/ (local only, never committed) and
  request-log lines
- **Hypotheses (not verified):** possible explanations, each marked as a guess
- **Open questions:** what to test next
```
