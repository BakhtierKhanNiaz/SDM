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
