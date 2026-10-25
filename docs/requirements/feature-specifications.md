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

## FEAT-005: Queue, scheduler, automatic retries and categories (M6)

- **Purpose:** Decide which downloads run, in what order and when; recover from temporary
  failures without help; label files by type.
- **Based on:** Project goals (brief §1). IDM: categories with folders (OBS-001, 002, 005);
  OBS-006's queue that retries until success. Rules: ADR-0013.

| ID | Requirement | Tests |
|---|---|---|
| FR-1 | Waiting downloads start in queue order, up to the limit (1-8, default 3) | `test_starts_in_queue_order_up_to_the_limit`, `test_limit_and_queue_order` |
| FR-2 | Moving an entry changes the order; the selection follows it | `test_reorder`, `test_start_now_and_move_from_the_window` |
| FR-3 | Raising the limit starts more at once; lowering it sends the last back to waiting, keeping what arrived | `test_raising_the_limit_starts_more_at_once`, `test_lowering_the_limit_sends_the_last_back_to_waiting` |
| FR-4 | Schedule: start/stop times and days, overnight windows; outside them running downloads go back to waiting | `test_overnight_window_belongs_to_the_day_it_starts`, `test_schedule_starts_and_stops_the_queue` |
| FR-5 | Start now ignores the limit and the schedule | `test_start_now_ignores_a_closed_schedule` |
| FR-6 | Temporary failures retry after about 1, 5 and 15 minutes, resuming; then they stay failed; 404 isn't retried | `test_temporary_failure_retries_automatically`, `test_after_three_retries_it_stays_failed`, `test_missing_file_is_not_retried` |
| FR-7 | Add without starting | `test_add_without_starting`, `test_add_url_dialog_can_add_without_starting` |
| FR-8 | Categories from the file type; optional subfolders (off by default) | `test_category_for`, `test_category_and_optional_subfolder`, `test_subfolders_are_off_by_default` |
| FR-9 | Category column and filter; filtered rows act on the right download | `test_category_column_and_filter` |
| FR-10 | Settings survive a restart; bad saved values fall back to defaults | `test_queue_settings_survive_a_restart`, `test_bad_saved_settings_fall_back_to_defaults` |

### Acceptance criteria

- All tests above pass; ruff is clean.
- One real-world download waits for its schedule window, then completes with a matching
  SHA-256 (owner approves the URL). Done 2026-10-19: waited about 90 s, started 1.7 s after
  the window opened, SHA-256 matched (roadmap).

## FEAT-006: "Download with SDM" from Chrome (M7)

- **Purpose:** Send a link from the browser to SDM without copying and pasting it.
- **Based on:** Project goals (brief §1: explicit browser handoff). Rules: ADR-0014, security
  rules 6 and 7. IDM's browser integration was not observed.
- **User workflow:** right-click a link, choose Download with SDM; SDM comes forward (it
  starts if needed) with the Add URL dialog filled in; check the folder, press Download.

| ID | Requirement | Tests |
|---|---|---|
| FR-1 | The menu item appears on http and https links only; other links are never sent | `handoff.test.js`, `background.test.js` |
| FR-2 | The extension asks only for `contextMenus` and `nativeMessaging` | `the extension asks for no more than two permissions` |
| FR-3 | Only the exact request schema is accepted; extra fields, other types, unsafe URLs and oversized or broken frames are refused with a generic error | `test_bridge_protocol.py`, `test_bridge_hostile_messages.py` |
| FR-4 | The host hands the link to the running SDM over the authenticated pipe; a wrong key is refused | `test_a_request_with_the_right_key_reaches_the_app`, `test_the_wrong_key_is_refused_and_the_listener_carries_on` |
| FR-5 | If SDM isn't running, the host starts it and waits up to 15 s | `test_starts_sdm_when_it_isnt_running_and_waits_for_it`, `test_gives_up_if_sdm_never_starts` |
| FR-6 | Misbehaving clients (dropped, silent, oversized, pickled) don't stop the listener | `test_a_silent_client_doesnt_block_others`, `test_a_silent_client_is_cut_off`, `test_an_oversized_message_is_dropped`, `test_pickled_objects_are_never_unpickled` |
| FR-7 | A handoff opens Add URL filled in; nothing is added until the user confirms; the URL is checked again | `test_window_handoff.py` |
| FR-8 | Handoffs wait their turn; more than 5 waiting are answered "busy" | `test_several_handoffs_wait_their_turn`, `test_too_many_waiting_handoffs_are_refused` |
| FR-9 | Only one SDM runs at a time | `test_only_one_listener_per_pipe`; launch check (roadmap) |
| FR-10 | Install and uninstall write and remove exactly the manifest, launcher and registry value, for one extension ID | `test_bridge_install.py` |

### Acceptance criteria

- All tests above pass; ruff is clean; `node --test` passes.
- In a separate Chrome profile, the owner loads the extension, registers it (after approving
  the registry change), and a right-click handoff opens SDM's dialog filled in, both with SDM
  running and with SDM closed. Done 2026-10-19 (in the owner's main profile): SDM closed →
  started and showed the dialog; SDM running → a python.org installer downloaded completely;
  Cancel added nothing (roadmap).

## FEAT-007: Browser context and automatic capture (M8)

- **Purpose:** Downloads from Chrome behave in SDM as they would in Chrome, and ordinary clicks
  can go to SDM.
- **Based on:** Project goals (brief §1, §6: consent for automatic capture). Rules: ADR-0015.
  IDM's capture was not observed.
- **User workflow:** install the extension (since 1.0.1 capture is on from then; the toolbar
  panel's "Send my downloads to SDM" turns it off); click any download link; SDM's dialog
  appears with the name and size; press Download.

| ID | Requirement | Tests |
|---|---|---|
| FR-1 | The Referer follows the browser's rule, per redirect hop, on every connection and resume | `test_referrer.py`, `test_browser_context.py`, `test_a_resume_after_a_restart_sends_the_same_referer` |
| FR-2 | A redirect from https to http is refused for every download | `test_https_to_http_redirects_are_refused`, `test_a_redirect_from_https_to_http_is_refused` |
| FR-3 | The browser's name is used when the server gives none, sanitized; the server's wins | `test_the_browsers_name_is_used_when_the_server_gives_none`, `test_the_servers_name_wins_over_the_browsers`, `test_the_browsers_name_is_sanitized` |
| FR-4 | Version 2 hints are optional and strictly checked; no cookies, headers or paths | `test_bridge_v2_messages.py` |
| FR-5 | The history keeps the hints (schema 5) | `test_the_history_keeps_the_hints`, `test_upgrading_to_version_5_keeps_old_entries` |
| FR-6 | Capture is on from installation (1.0.1; `downloads` asked for at install); the panel's switch turns it off and on, remembered | `popup.test.js`, `with the panel's switch off nothing is touched...`, `with the panel's switch off, nothing is captured` |
| FR-7 | Captured: Chrome's copy cancelled and erased before SDM is asked; finished ones stay | `right after installing, Chrome's copy is stopped...`, `a download that finished before it could be stopped stays in Chrome` |
| FR-8 | Skipped: incognito, blob:/data:, below the minimum size, our own restarts | `capture.test.js`, `background.test.js` |
| FR-9 | If SDM can't take it, Chrome downloads it, without a loop | `when SDM can't take it, Chrome downloads it after all`, `the download Chrome restarts for SDM isn't captured again (no loop)` |
| FR-10 | Right-click on video and audio sends the player's address | `a right-click on a player sends the player's own address` |
| FR-11 | The dialog shows the browser's information as plain text; editing the address drops it | `test_the_dialog_says_what_the_browser_knew`, `test_a_file_name_is_shown_as_text_never_as_html`, `test_editing_the_address_drops_the_hints` |

### Acceptance criteria

- All tests above pass; ruff is clean; `node --test` passes.
- With capture on in the owner's Chrome, a normal click on python.org's
  `python-3.14.7-embed-amd64.zip` opens SDM's dialog, Chrome's own copy disappears, and SDM's
  file matches python.org's SHA-256. Done 2026-10-20 (roadmap).

## FEAT-008: Settings, speed limit, checksums, tray and notifications (M9)

- **Purpose:** Day-to-day comfort: limit bandwidth, check files, be told when downloads finish,
  find the files.
- **Based on:** Project goals (brief §1). IDM: completion dialog with "Don't show this dialog
  again" (OBS-001). Rules: ADR-0016.

| ID | Requirement | Tests |
|---|---|---|
| FR-1 | One speed limit for all downloads and connections; changes act at once | `test_limiter.py`, `test_split_connections_share_the_limit`, `test_lifting_the_limit_speeds_up_a_running_download` |
| FR-2 | Connections per download 1-8; 1 never splits | `test_one_connection_per_download_never_splits` |
| FR-3 | SHA-256 accepted as printed; malformed refused; finished files verified, mismatch kept | `test_checksums_and_preferences.py`, `test_a_matching_checksum_is_verified`, `test_a_mismatch_keeps_the_file_and_says_so`, `test_add_url_checks_the_sha256_box` |
| FR-4 | Settings saved; damaged values fall back to defaults | `test_preferences_default_and_round_trip`, `test_damaged_settings_fall_back_to_defaults`, `test_settings_dialog_round_trip` |
| FR-5 | Notifications for finished, verified, mismatch and final failures; can be switched off | `test_notifications_follow_the_downloads`, `test_finishing_and_failing_are_announced_once`, `test_notifications_can_be_switched_off` |
| FR-6 | Optional close-to-tray; Exit/Quit really quit | `test_closing_hides_to_the_tray_when_chosen`, `test_without_the_option_closing_quits` |
| FR-7 | Right-click menu; Show in folder only for SDM's own finished file; no Open | `test_the_right_click_menu`, `test_show_in_folder_only_for_sdms_own_finished_file` |
| FR-8 | Total speed in the status bar, which stays visible; window size, columns and last folder remembered | `test_status_bar_shows_the_total_speed`, `test_the_status_line_survives_hovering_over_buttons`, `test_the_window_layout_is_remembered`, `test_the_last_folder_is_offered_next_time` |

### Acceptance criteria

- All tests above pass; ruff is clean.
- The owner, in their own SDM: python.org's `python-3.14.7-embed-amd64.zip` with a 1 MB/s limit
  takes about 12 s, finishes as "Completed · verified" with the published SHA-256, and a
  Windows notification appears. Done 2026-10-20 (roadmap).

## FEAT-009: Convert a file with ffmpeg (M12a)

- **Purpose:** Turn a downloaded video into music (MP3, M4A) or a widely playable MP4.
- **Based on:** The owner's request (M12, option B). Rules: ADR-0020. IDM's converter (if
  any) was not observed.
- **User workflow:** right-click a finished download → **Convert…** (or Tools → Convert
  file… and Browse), choose the format, press Convert; watch the bar; Show in folder.

| ID | Requirement | Tests |
|---|---|---|
| FR-1 | ffmpeg is found from Settings, PATH or WinGet's folders; without it, the window says how to install it | `test_finding_ffmpeg`, `test_without_ffmpeg_the_window_says_how_to_get_it`, `test_settings_show_and_keep_where_ffmpeg_is` |
| FR-2 | A fixed command line: `file:` paths, `-nostdin -n`, no shell | `test_the_command_line_is_fixed_and_never_overwrites`, `test_converting_makes_a_new_file_and_keeps_the_original` |
| FR-3 | The result is a new file next to the source, numbered if taken; the source is unchanged | `test_the_result_is_a_new_file_next_to_the_source`, `test_a_second_conversion_gets_a_numbered_name` |
| FR-4 | Progress from ffmpeg's duration and `-progress` lines | `test_progress_from_ffmpegs_output` |
| FR-5 | Failure is explained (no sound, no video, missing encoder, else ffmpeg's last line); failure and Cancel delete the partial file | `test_known_failures_are_explained_in_plain_words`, `test_a_failure_shows_ffmpegs_reason_and_deletes_the_partial_file`, `test_cancel_stops_ffmpeg_and_deletes_the_partial_file`, `test_a_program_that_cant_start_is_reported`, `test_a_video_without_sound_is_explained` |
| FR-7 | With the real ffmpeg (skipped where it isn't installed): MP3, M4A and MP4 have the right codecs and length; the bar moves | `test_convert_real_ffmpeg.py` |
| FR-6 | Convert… only for SDM's own finished files | `test_convert_is_offered_for_finished_files` |

### Acceptance criteria

- All tests above pass; ruff is clean.
- Real ffmpeg 9.0.2 (gyan.dev, installed with winget in Claude's sandbox, 2026-10-25):
  synthetic VP9/Opus WebM → MP3, M4A and MP4 (H.264 640×360 + AAC, 6.00 s each), FLAC → MP3,
  a second copy numbered, a silent video explained; checked with ffprobe. Done.
- The owner, in their own SDM: a downloaded video becomes a playable MP3 and MP4. Not yet done.

## FEAT-010: Video pages with yt-dlp, optional (M12b)

- **Purpose:** Download a video page in a chosen quality, like a file: in the list, with
  pause, resume, cancel and the history.
- **Based on:** The owner's request (M12, option B). Rules: ADR-0020. IDM's video features
  were not observed.
- **User workflow:** Settings > Media: tick "Enable video-page downloads" and accept the
  notice (once). Add URL: paste the page's address, choose "Download as: Video page: 1080p"
  (or 720p, 4K, MP3, M4A), Download.

| ID | Requirement | Tests |
|---|---|---|
| FR-1 | Off by default; turning it on shows the terms notice once; without it, video downloads fail with a reason | `test_turning_the_add_on_on_shows_the_notice`, `test_the_notice_isnt_shown_again_once_accepted`, `test_add_url_offers_video_pages_only_when_turned_on`, `test_turned_off_or_missing_yt_dlp_is_explained` |
| FR-2 | A locked-down command line: `--ignore-config` first, no cookies, logins or `--exec`, the address after `--` | `test_the_command_line_is_locked_down`, `test_a_video_page_downloads_into_one_file` |
| FR-3 | The page's host passes the network policy before yt-dlp starts | `test_a_page_on_this_computer_is_blocked_before_yt_dlp_starts` |
| FR-4 | One finished file in the folder (merged video, or MP3/M4A), never overwriting; the work folder is removed | `test_a_video_page_downloads_into_one_file`, `test_audio_only_becomes_an_mp3`, `test_a_second_copy_gets_a_numbered_name`, `test_the_finished_file_is_the_merged_one` |
| FR-5 | Pause keeps yt-dlp's partial files and resume continues them; Cancel (running or paused) deletes them; closing SDM pauses | `test_pause_keeps_the_partial_files_and_resume_continues`, `test_cancel_stops_yt_dlp_and_deletes_its_files`, `test_cancelling_a_paused_video_deletes_its_files`, `test_closing_sdm_pauses_a_running_video` |
| FR-6 | Failures in plain words (unsupported page, quality, DRM, login, missing ffmpeg, HTTP errors); a failure that left nothing leaves no work folder | `test_failures_in_plain_words`, `test_an_unsupported_page_fails_with_a_plain_reason`, `test_a_missing_page_is_explained_and_leaves_nothing` |
| FR-7 | The history keeps the quality (schema 7) | `test_upgrading_the_history_to_version_7_keeps_entries` |

### Acceptance criteria

- All tests above pass (with a fake yt-dlp); ruff is clean.
- Real yt-dlp 2026.10.21 and ffmpeg 9.0.2 (winget, in Claude's sandbox, 2026-10-25), against a
  test server on 127.0.0.1 only (`test_video_real_ytdlp.py`, skipped where they aren't
  installed): an HTML page with a `<video>` came out as 1080p MP4 (H.264 + AAC) and as MP3, a
  direct `.mp4` link as 720p MP4, each the only file left in the folder; a missing page said
  "The page wasn't found (HTTP 404)." and left nothing. Done.
- The owner, on a real video page they may download: a playable 1080p MP4 and an MP3. Not
  yet done.

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
