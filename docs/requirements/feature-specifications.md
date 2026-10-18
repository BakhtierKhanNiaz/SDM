# Feature specifications

Requirements for each SDM feature (Stage B), based on observations and project goals. A
feature reaches *Specified* in the [parity matrix](../feature-parity-matrix.md) once its spec
is here.

## FEAT-001: Single-connection download (M2)

- **Purpose:** Save one file from an http/https URL, reliably and safely.
- **Based on:** Project goals (brief §5) and the IDM comparison OBS-001 to OBS-006 in
  [behavior-observations.md](../research/behavior-observations.md).
- **User workflow:** `uv run sdm-get <URL> [--dest FOLDER] [--allow-local-network]` →
  progress line → "Saved <path> (<size>)" or "Error: <reason>". When the server gives no size,
  a warning follows the "Saved" line. (Window integration: M3.)

### Functional requirements

| ID | Requirement | Tests |
|---|---|---|
| FR-1 | Accept only `http`/`https` URLs without embedded credentials, spaces or control characters | `tests/unit/test_urls.py` |
| FR-2 | Refuse destinations the network policy blocks (ADR-0007), on every redirect hop | `tests/unit/test_policy.py`, `tests/security/test_unsafe_targets.py` |
| FR-3 | Follow 301/302/303/307/308 redirects, relative or absolute, at most 10 | `test_follows_redirects...`, `test_redirect_loop_is_stopped` |
| FR-4 | Treat only `200` as success; fail immediately on other 4xx (404 and 410 reported as "not found", OBS-003); retry 408, 429, 5xx | `test_missing_file_fails_without_retrying`, `test_other_client_errors_are_refusals`, `test_temporary_server_error...`, `test_429...` |
| FR-5 | Retry transient failures up to 3 attempts in total, waiting 1 s, 2 s, ... or the server's `Retry-After` (max 60 s) | `test_gives_up_after_max_attempts`, `tests/unit/test_retry_after.py` |
| FR-6 | Request `Accept-Encoding: identity` and save bytes unchanged | `test_sends_identity_encoding...`, `test_downloads_the_file_byte_for_byte` |
| FR-7 | Handle unknown sizes (no `Content-Length`). When only the closing connection marks the end, say that completeness can't be confirmed (OBS-005); a chunked response counts as complete only after its final chunk | `test_unknown_size`, `test_chunked_download_counts_as_complete`, `test_chunked_download_cut_before_the_last_chunk_fails`, `test_warns_only_when_completeness_cant_be_confirmed` |
| FR-8 | With a known size, the byte count must match, or the attempt fails (retryable) | `test_cut_connection_is_retried`, `test_always_cut_connection...` |
| FR-9 | Name and sanitize the file per ADR-0008 | `tests/unit/test_filenames.py`, `test_name_from_content_disposition`, hostile-filename tests |
| FR-10 | Never overwrite: `name (1).ext` and so on; leave other partial files alone | `test_existing_files_are_never_overwritten`, `test_another_downloads_partial_file...` |
| FR-11 | Check free disk space first when the size is known | `test_not_enough_disk_space...` |
| FR-12 | Connect timeout 15 s; fail after 30 s without data | `test_silent_server_times_out`, `test_connection_refused` |
| FR-13 | Cancelling stops promptly and deletes the partial file | `test_cancelling_deletes_the_partial_file` |
| FR-14 | Report progress as (bytes received, total or None) | `test_downloads_the_file_byte_for_byte`, `test_unknown_size` |
| FR-15 | Explain blocked writes, including Controlled Folder Access's misleading "file not found" | `test_blocked_writes_are_explained`, `test_disk_filling_up_while_writing` |
| FR-16 | Never log credentials or query strings | `tests/unit/test_urls.py` (redaction) |

### Error conditions

Every failure raises an `SDMError` subclass with a message meant for the user. The command
line prints `Error: <message>` and exits with code 1. Ctrl+C exits with 130 after deleting
the partial file.

### Acceptance criteria

- All tests listed above pass; ruff is clean.
- A real-world download from a URL the owner chooses succeeds (manual demonstration). Done
  2026-10-17: python.org's `python-3.14.7-embed-amd64.zip`, SHA-256 matched the published
  value (details in the [roadmap](../roadmap.md)).
- Compared with IDM for the planned scenarios before the feature counts as *Verified*. Done
  2026-10-18 (OBS-001 to OBS-006); the differences are explained in
  [behavior-observations.md](../research/behavior-observations.md#idm-vs-sdm).

### Open questions (to answer by observing IDM)

- Answered: IDM asks before adding a duplicate URL and offers a numbered `name_2.ext`
  (OBS-002). With an unknown size it saves the file and warns (OBS-005). With a cut
  connection it tries to resume and stops when the server can't (OBS-006).
- Still open: how many automatic retries IDM makes, and with what delays (OBS-006).
- Still open: whether IDM picks a filename from the `Content-Type` when the URL has no
  extension.

## FEAT-002: Downloads in the window, with history (M3)

- **Purpose:** Start, watch and cancel downloads from the window, and keep a history that
  survives restarts.
- **Based on:** Project goals (brief §1). IDM observations: OBS-002 (duplicate URL),
  OBS-003 and OBS-006 (the list keeps failed entries), OBS-005 (no size for unknown sizes).
- **User workflow:** Add URL (Ctrl+N) → enter the address, the folder, and optionally allow
  the local network → Download → watch the row → Cancel if needed → Remove from list when done.

| ID | Requirement | Tests |
|---|---|---|
| FR-1 | Downloads run off the main thread; the window never waits on the network | `tests/integration/test_manager.py` |
| FR-2 | At most 3 run at once; the rest show "Queued" and start in order | `test_at_most_n_downloads_run_at_once`, `test_three_at_once_the_rest_wait` |
| FR-3 | A row shows name, size, percent (or bytes when the size is unknown), speed, time left and status, updated about 5 times a second | `test_download_model.py`, `test_live_progress_and_speed_reach_the_table` |
| FR-4 | Speed and time left are averaged over the last 3 s | `test_progress.py` |
| FR-5 | Cancel stops a running or waiting download promptly and deletes its partial file | `test_cancel_then_remove_from_the_window`, `test_cancelling_a_waiting_download` |
| FR-6 | Remove from list deletes the entry, never the file; active entries can't be removed | `test_remove_deletes_the_entry_but_not_the_file`, `test_active_downloads_cannot_be_removed` |
| FR-7 | The history survives restarts; failed entries keep their message (tooltip) | `test_history_survives_a_restart`, `test_failure_is_recorded_with_its_message` |
| FR-8 | Adding a URL that was downloaded before shows a warning; nothing is overwritten | `test_warns_when_the_url_was_downloaded_before` |
| FR-9 | Unsafe or invalid URLs and missing folders are refused before anything is saved | `test_unsafe_urls_are_refused_before_anything_is_saved`, dialog tests |
| FR-10 | Quitting with downloads running asks first; "Yes" cancels them | `test_closing_with_downloads_running_asks_first` |
| FR-11 | After a crash, unfinished entries show "Interrupted"; a corrupted history is set aside with a notice | `test_a_crash_leaves_entries_interrupted`, `test_corrupted_database_is_set_aside_and_replaced`, `test_startup_notices` |
| FR-12 | "Completed (size unconfirmed)" when only the connection closing marked the end | `test_completed_without_a_size_says_so` |

### Acceptance criteria

- All tests above pass; ruff is clean.
- `uv run python app.py` opens the window and closes cleanly.
- One real-world download through the window succeeds (manual demonstration; the owner
  approves the URL). Done 2026-10-19: python.org's zip, SHA-256 matched, and it was saved as
  `(1)` beside the earlier copy (details in the [roadmap](../roadmap.md)).

### Open questions

- How IDM shows live progress for unknown sizes (re-run R1).
- Pausing, and resuming interrupted entries: M4.

## FEAT-003: Pause, resume and crash recovery (M4)

- **Purpose:** Stop a download and continue it later, also after quitting or a crash,
  without downloading again what already arrived, and without ever mixing two versions of a
  file.
- **Based on:** Project goals (brief §1, §5). IDM observation OBS-006 (resume with `Range`,
  64 bytes early; a `200` means no resume support). Rules: ADR-0011.

| ID | Requirement | Tests |
|---|---|---|
| FR-1 | Pause keeps the partial file; the entry shows Paused with its percent | `test_pause_then_resume`, `test_pause_and_resume_buttons` |
| FR-2 | Resume asks for the rest (`Range` + `If-Range`) and finishes with the right content | `test_pause_and_resume_in_a_later_call`, `test_cut_download_continues_where_it_stopped` |
| FR-3 | Only an exact `206` continues; `200`, a wrong range, a changed size or tag restart from 0 | `test_server_that_ignores_range_restarts_cleanly`, `test_wrong_content_range_restarts`, `test_file_changed_on_the_server_is_downloaded_whole`, `test_changed_size_restarts` |
| FR-4 | Without version tags, a 64-byte overlap is checked | `test_without_version_tags_the_last_64_bytes_are_checked`, `test_silent_change_is_caught_by_the_64_byte_check` |
| FR-5 | A `416` when everything is already there finishes the download | `test_everything_already_there_finishes_on_416` |
| FR-6 | Automatic retries continue instead of restarting | `test_retries_only_ask_for_the_missing_bytes` |
| FR-7 | Cancel deletes the partial file (running, waiting or paused); Remove deletes an unfinished entry's partial file | `test_cancelling_a_paused_download_deletes_its_partial`, `test_removing_a_paused_download_deletes_its_partial` |
| FR-8 | A failed download keeps its partial file only if the server can resume; Retry continues | `test_failure_keeps_the_partial_file_when_the_server_can_resume`, `test_retry_after_a_failure_continues_where_it_stopped` |
| FR-9 | Quitting pauses running downloads; nothing resumes on its own at startup | `test_closing_with_downloads_running_asks_first`, `test_quit_question_says_downloads_will_be_paused` |
| FR-10 | After a crash, interrupted entries resume from their partial file (Resume / Resume all) | `test_resume_after_a_crash`, `test_resume_all_button` |
| FR-11 | Pausing on a server that can't resume asks first | `test_pausing_on_a_server_that_cant_resume_asks_first` |
| FR-12 | Partial-file paths from the database are used or deleted only inside the entry's folder | `test_partial_path_outside_the_download_folder_is_ignored` |
| FR-13 | The history upgrades from schema 1 to 2 without losing entries | `test_upgrade_from_version_1_keeps_history` |

### Acceptance criteria

- All tests above pass; ruff is clean.
- One real-world pause, SDM restart and resume finishes with a SHA-256 matching the
  publisher's (owner approves the URL). Done 2026-10-19: python.org's zip paused at 31%,
  resumed from exactly that point after a restart, and matched (details in the
  [roadmap](../roadmap.md)).

## FEAT-004: Parallel segmented downloads (M5)

- **Purpose:** Download a big file over several connections at once, faster when a server
  limits each connection, without ever assembling a wrong file.
- **Based on:** Project goals (brief §1, §5). OBS-001 and OBS-004 (IDM: 8 connections, extra
  connections at the final URL, dropped on `200`). Rules: ADR-0012.

| ID | Requirement | Tests |
|---|---|---|
| FR-1 | Split files of at least 2 MiB into parts of at least 1 MiB, over up to 8 connections | `test_segments.py`, `test_big_file_is_split_and_assembled` |
| FR-2 | Split only if the server advertises ranges and gives a version tag; otherwise one connection | `test_one_connection_when_splitting_isnt_safe_or_useful` |
| FR-3 | Accept a part only from a `206` with the exact `Content-Range` and the same tags | `test_wrong_content_range_on_one_part_falls_back`, `test_content_range.py` |
| FR-4 | Fall back to one connection when a part can't be trusted while the first is open | `test_server_that_ignores_range_falls_back`, `test_file_changing_right_after_the_first_request_gives_one_consistent_version` |
| FR-5 | A dropped part retries only its own remaining range | `test_a_dropped_part_retries_only_its_remainder`, `test_two_parts_dropped_at_once`, `test_first_connection_dropped_continues_with_a_range` |
| FR-6 | Pause, quit, crash and resume continue part by part; a damaged map starts over | `test_resume_asks_only_for_the_missing_ranges`, `test_pause_and_resume_a_split_download`, `test_pause_quit_restart_and_resume_a_split_download`, `test_damaged_parts_map_is_ignored` |
| FR-7 | Free connections take over half of the part with the most left | `test_a_resume_fills_free_connections_by_halving`, `test_a_connection_that_finishes_early_helps_the_slowest` |
| FR-8 | Faster against a per-connection speed limit | `test_split_download_beats_a_per_connection_speed_limit` (4.0 s vs 1.0 s) |
| FR-9 | The window shows the connection count while downloading | `test_a_split_download_shows_its_connections` |
| FR-10 | Partial files are sparse on NTFS; progress is durable before it is recorded | `test_partial_files_are_marked_sparse_on_ntfs` |

### Acceptance criteria

- All tests above pass; ruff is clean.
- One real-world segmented download matches the publisher's SHA-256 (owner approves the URL).
  Done 2026-10-19: python.org's zip over up to 8 connections, SHA-256 matched (roadmap).

## Template

```markdown
## FEAT-00N: <feature name>

- **Purpose:** why the user needs it
- **Based on:** OBS-xxx entries, documentation links, or "project goal"
- **User workflow:** numbered steps
- **Functional requirements:** FR-1, FR-2, ... (each testable)
- **Expected behavior:** including states and transitions
- **Error conditions:** what can go wrong and what the user sees
- **Acceptance criteria:** how we know it's done
- **Test cases:** linked to test files once written
- **Dependencies / open questions:**
```
