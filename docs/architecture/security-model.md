# Security model

Status: **M9.** Rules marked *Implemented* have code and tests; the others are planned for
the milestone listed.

## Trust boundaries

| Input | Trust | Where it enters |
|---|---|---|
| URLs, redirects, response headers, file contents | Untrusted | engine (M2) |
| Filenames from URLs or `Content-Disposition` | Untrusted | engine (M2) |
| Messages from the browser extension | Untrusted | bridge (M7) |
| User input in the SDM window or `sdm-get` | Trusted intent, still validated | ui, cli |
| Local database and settings | Trusted, but must survive corruption | storage (M3) |

## Rules

| # | Rule | Status |
|---|---|---|
| 1 | **Protocols:** only `http` and `https`, on the first request and every redirect hop. No embedded `user:pass@` credentials. No redirect from `https` down to `http` (M8, ADR-0015). | Implemented (M2, M8) — `sdm.core.urls`, `sdm.core.referrer.check_redirect` |
| 2 | **Destinations:** ADR-0007. Loopback, link-local, multicast, unspecified and reserved addresses are blocked. Private networks need `--allow-local-network`. IP literals are checked per hop, and hostnames after DNS inside aiohttp's resolver. | Implemented (M2) — `sdm.engine.policy` |
| 3 | **Filenames:** one sanitized Windows component (ADR-0008). Never written outside the chosen folder. Length fits the 260-character path limit. Bidi-control spoofing removed. | Implemented (M2) — `sdm.core.filenames` |
| 4 | **No overwrite:** existing files are never replaced. A taken name becomes `name (n).ext`. | Implemented (M2) |
| 5 | **Never execute** downloaded files, and never open them automatically. SDM has no "Open file": only "Show in folder", which selects the file in Explorer (M9). A checksum mismatch warns not to run the file. | Holds: no code opens downloads (`test_the_right_click_menu`) |
| 6 | **No local HTTP server.** Browser communication goes only through Chrome Native Messaging, restricted to SDM's own extension ID. The host reaches the app over a named pipe that both sides authenticate with a per-user key (`%LOCALAPPDATA%\SDM\bridge.key`); no network port is opened (ADR-0014). | Implemented (M7) — `test_bridge_pipe.py`, `test_bridge_install.py` |
| 7 | **Browser messages:** exactly `{version: 1, type: "download", url}` or version 2 with the optional, strictly checked hints of ADR-0015 (a bare file name, never a path), at most 64 KiB, checked in the host and again in the app. No filesystem operations or paths. Generic error replies. JSON only, never pickle. A handoff only fills in the Add URL dialog; the user confirms. | Implemented (M7) — `test_bridge_hostile_messages.py`, `test_bridge_host.py`, `test_window_handoff.py` |
| 8 | **Secrets:** logs show URLs without credentials or query strings (`redact_url`). Cookies and authorization headers are never logged. | Implemented for URLs (M2); headers when auth arrives |
| 9 | **Privacy:** no browsing-history collection beyond explicit handoffs, and downloads the user chose to capture. Capture is off by default, needs the user to grant `downloads` in Chrome's own prompt, and never touches Incognito. The Referer follows the browser's rule (origin only to other sites, nothing from https to http) and is never logged; the window shows only the page's host. No cookies are read or forwarded. No data sent to third parties. | Holds (M8: `popup.test.js`, `test_referrer.py`) |
| 10 | **Dependencies:** free/open-source only, license and support checked, versions pinned in `uv.lock`. | Holds (ADR-0001, ADR-0006) |
| 11 | **Proxies:** proxy environment variables are ignored, because a proxy would hide the real destination from rule 2. | Implemented (M2) |
| 12 | **History database:** per-user `%LOCALAPPDATA%\SDM\sdm.db`. Full URLs are stored (they may hold tokens, ADR-0010) but never logged. Every query uses `?` parameters. A corrupted file is set aside, never deleted. | Implemented (M3a) — `sdm.storage.database`, `test_urls_are_stored_as_data_not_sql` |
| 14 | **Resume integrity:** a resume continues the file only on a `206` whose `Content-Range` starts exactly where the partial file ends, with the same total and version tags (or a matching 64-byte overlap). Otherwise it restarts, so versions are never mixed. `Content-Range` is parsed strictly (ASCII digits, consistent bounds) (ADR-0011). | Implemented (M4) — `tests/integration/test_resume.py`, `test_content_range.py` |
| 15 | **Paths from the database** are used only inside the entry's folder: partial files must be `.sdmpart` files directly in it (M4), and Show in folder and checksum checks use only the finished file directly in it (M9, `finished_file`), so a tampered database can't point SDM elsewhere. | Implemented (M4, M9) — `test_partial_path_outside_the_download_folder_is_ignored`, `test_show_in_folder_only_for_sdms_own_finished_file` |
| 16 | **Segmented integrity:** parts come only from `206` replies with the exact requested `Content-Range` and the same version tags, at the final URL through the same redirect checks and policy. Doubt means one connection; a saved parts map that doesn't cover the file exactly is ignored (ADR-0012). | Implemented (M5) — `test_segmented.py`, `test_segments.py` |
| 13 | **Engine thread:** the window never runs network code, and only the main thread writes the database (ADR-0009). Every download submitted to the manager still goes through rule 2's policy. | Implemented (M3a) — `test_default_policy_blocks_this_computer` |

Disguised spellings of loopback (`127.1`, `2130706433`, `0x7f000001`, `127.000.000.001`)
never reach the target: aiohttp rejects non-canonical IPv4 forms, and Windows DNS can't
resolve the hex form (`test_disguised_spellings_of_this_computer_never_reach_it`).

## Known gaps (to revisit)

- NAT64 (`64:ff9b::/96`) and 6to4 (`2002::/16`) IPv6 addresses that embed a private IPv4
  address are not unwrapped before checking.
- The bridge pipe accepts remote (SMB) clients by default; they would need this account's
  credentials and the bridge key. Any program running as this user can read the key and
  hand SDM links, but only through the same schema and confirmation dialog (ADR-0014).
- Captured downloads are requested again by SDM with GET: a download Chrome started with a
  POST form can't be reproduced, and one that needs the site's cookies fails in SDM (the
  owner chose not to forward cookies, ADR-0015).
- A server that sends no `Content-Length` and closes early is indistinguishable from a
  complete download (inherent to HTTP). Integrity checks (M9) can help when a checksum is known.

## Environment notes

- Windows Controlled Folder Access is on. A blocked write surfaces in Python as
  `FileNotFoundError` (errno 2), even though the folder exists (observed 2026-10-17). SDM
  translates both that and `PermissionError` into a message that names Controlled Folder Access.
