# Security model

Status: **M10.** Rules marked *Implemented* have code and tests; the others are planned for
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
| 2 | **Destinations:** ADR-0007. Loopback, link-local, multicast, unspecified and reserved addresses are blocked. Private networks need `--allow-local-network`. IP literals are checked per hop, and hostnames after DNS inside aiohttp's resolver. IPv4 hidden in IPv6 (mapped, NAT64, 6to4) is checked as IPv4 (M10). | Implemented (M2, M10) — `sdm.engine.policy`, `test_ipv4_hidden_inside_ipv6_is_checked_as_ipv4` |
| 3 | **Filenames:** one sanitized Windows component (ADR-0008). Never written outside the chosen folder. Length fits the 260-character path limit. Bidi-control spoofing removed. | Implemented (M2) — `sdm.core.filenames` |
| 4 | **No overwrite:** existing files are never replaced. A taken name becomes `name (n).ext`. | Implemented (M2) |
| 5 | **Never execute** downloaded files, and never open them automatically. SDM has no "Open file": only "Show in folder", which selects the file in Explorer (M9). A checksum mismatch warns not to run the file. | Holds: no code opens downloads (`test_the_right_click_menu`) |
| 6 | **No local HTTP server.** Browser communication goes only through Chrome Native Messaging, restricted to SDM's own extension ID. The host reaches the app over a named pipe that both sides authenticate with a per-user key (`%LOCALAPPDATA%\SDM\bridge.key`) and that refuses clients on other computers (M10); no network port is opened (ADR-0014). | Implemented (M7) — `test_bridge_pipe.py`, `test_bridge_install.py` |
| 7 | **Browser messages:** exactly `{version: 1, type: "download", url}` or version 2 with the optional, strictly checked hints of ADR-0015 (a bare file name, never a path; `source` is menu, capture or video, M12), at most 64 KiB, checked in the host and again in the app. No filesystem operations or paths. Generic error replies. JSON only, never pickle. A handoff only fills in the Add URL dialog; the user confirms. | Implemented (M7) — `test_bridge_hostile_messages.py`, `test_bridge_host.py`, `test_window_handoff.py` |
| 8 | **Secrets:** logs show URLs without credentials or query strings (`redact_url`), and the log file's `RedactingFilter` strips them from any address that still reaches a message or traceback (M10). Cookies and authorization headers are never logged. | Implemented (M2, M10) — `test_the_log_file_rotates_and_hides_secrets` |
| 9 | **Privacy:** no browsing-history collection beyond explicit handoffs, and downloads the user chose to capture. Since 1.0.1 capture is on from installation (owner's decision, ADR-0015): `downloads` is asked for in the browser's install prompt, the extension's description says it sends downloads to SDM, and its toolbar switch turns capture off. It never touches Incognito. The Referer follows the browser's rule (origin only to other sites, nothing from https to http) and is never logged; the window shows only the page's host. No cookies are read or forwarded. No data sent to third parties. | Holds (M8: `popup.test.js`, `test_referrer.py`) |
| 10 | **Dependencies:** free/open-source only, license and support checked, versions pinned in `uv.lock`. | Holds (ADR-0001, ADR-0006) |
| 11 | **Proxies:** proxy environment variables are ignored, because a proxy would hide the real destination from rule 2. | Implemented (M2) |
| 12 | **History database:** per-user `%LOCALAPPDATA%\SDM\sdm.db`. Full URLs are stored (they may hold tokens, ADR-0010) but never logged. Every query uses `?` parameters. A corrupted file is set aside, never deleted. | Implemented (M3a) — `sdm.storage.database`, `test_urls_are_stored_as_data_not_sql` |
| 14 | **Resume integrity:** a resume continues the file only on a `206` whose `Content-Range` starts exactly where the partial file ends, with the same total and version tags (or a matching 64-byte overlap). Otherwise it restarts, so versions are never mixed. `Content-Range` is parsed strictly (ASCII digits, consistent bounds) (ADR-0011). | Implemented (M4) — `tests/integration/test_resume.py`, `test_content_range.py` |
| 15 | **Paths from the database** are used only inside the entry's folder: partial files must be `.sdmpart` files directly in it (M4), and Show in folder and checksum checks use only the finished file directly in it (M9, `finished_file`), so a tampered database can't point SDM elsewhere. | Implemented (M4, M9) — `test_partial_path_outside_the_download_folder_is_ignored`, `test_show_in_folder_only_for_sdms_own_finished_file` |
| 16 | **Segmented integrity:** parts come only from `206` replies with the exact requested `Content-Range` and the same version tags, at the final URL through the same redirect checks and policy. Doubt means one connection; a saved parts map that doesn't cover the file exactly is ignored (ADR-0012). | Implemented (M5) — `test_segmented.py`, `test_segments.py` |
| 13 | **Engine thread:** the window never runs network code, and only the main thread writes the database (ADR-0009). Every download submitted to the manager still goes through rule 2's policy. | Implemented (M3a) — `test_default_policy_blocks_this_computer` |
| 17 | **Media tools (M12, ADR-0020):** ffmpeg (and yt-dlp, M12b) are programs the user installed, started with a fixed argument list and no shell. Files go in as `file:<absolute path>` so a name can't act as an option or protocol; `-nostdin -n` never overwrites; output is always a new file, and partial output is deleted on failure or Cancel. The source is only read. SDM ships neither tool. yt-dlp (M12b, off by default) runs with `--ignore-config`, `--no-playlist`, no cookies and no `--exec`, the address last after `--`, into `<folder>\.sdm-video-<id>`; only that exact folder is ever deleted; the host must pass the network policy first. | Implemented (M12a, M12b) — `test_media_ffmpeg.py`, `test_convert.py`, `test_media_ytdlp.py`, `test_video.py` |

Disguised spellings of loopback (`127.1`, `2130706433`, `0x7f000001`, `127.000.000.001`)
never reach the target: aiohttp rejects non-canonical IPv4 forms, and Windows DNS can't
resolve the hex form (`test_disguised_spellings_of_this_computer_never_reach_it`).

## Known gaps (to revisit)

- SDM started as administrator can't receive Chrome handoffs: Windows keeps the normal-level
  helper away from an elevated pipe. SDM warns at startup instead of failing silently (M10).
- Any program running as this user can read the bridge key and hand SDM links, but only
  through the same schema and confirmation dialog (ADR-0014). (Closed in M10: remote pipe
  clients are refused, and NAT64/6to4 addresses are checked as their IPv4 address.)
- Captured downloads are requested again by SDM with GET: a download Chrome started with a
  POST form can't be reproduced, and one that needs the site's cookies fails in SDM (the
  owner chose not to forward cookies, ADR-0015).
- Video pages (M12b, optional, off by default): SDM checks the page's host against the network
  policy before yt-dlp starts, but yt-dlp's own later requests (redirects, stream servers)
  aren't checked by SDM, and yt-dlp's code decides what it fetches. Mitigations: off until the
  user accepts a notice, `--ignore-config`, no cookies or logins, a fixed argument list with
  the address after `--`, files only in SDM's own work folder (ADR-0020). SDM's speed limit
  doesn't apply to yt-dlp.
- A server that sends no `Content-Length` and closes early is indistinguishable from a
  complete download (inherent to HTTP). Integrity checks (M9) can help when a checksum is known.

## Environment notes

- Windows Controlled Folder Access is on. A blocked write surfaces in Python as
  `FileNotFoundError` (errno 2), even though the folder exists (observed 2026-10-17). SDM
  translates both that and `PermissionError` into a message that names Controlled Folder Access.

## Dependency audit

- 2026-10-20: `pip-audit` 2.10.1 on every locked package (runtime and development: aiohttp
  3.14.5, PySide6-Essentials 6.12.0, pytest 9.1.1, ruff 0.17.1 and their dependencies, 20 in
  all): no known vulnerabilities (ADR-0017). Repeat before each release.
- 2026-10-20, after adding PyInstaller (27 packages): no known vulnerabilities (ADR-0018).
