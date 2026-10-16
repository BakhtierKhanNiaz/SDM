# M0 environment report (2026-10-17)

What was on the development machine when the project started. Everything here was checked
with commands. Nothing is assumed.

## Machine

| Item | Value |
|---|---|
| OS | Windows 10 Pro 10.0.19045 |
| CPU / RAM | Intel Core i3-8100 / 7.9 GB |
| Free disk | C: 35.8 GB, D: 110.4 GB (project lives on D:) |
| Browsers | Chrome 155.0.8059.80, Edge 155.0.4283.45 (both Chromium) |

## Tools

| Tool | Version | Notes |
|---|---|---|
| Python | 3.14.7, 64-bit | Only Python installed. Bundled SQLite 3.50.4, OpenSSL 3.5.7 |
| uv | 0.12.5 | Manages `.venv` and dependencies |
| pip | 26.2.1 | Not used directly for SDM |
| Git | 2.55.0.windows.5 | Installed during M1 with winget |
| Node.js / npm | 24.20.0 / 11.19.0 | Not needed yet |
| VS Code | 1.142.0 | |
| winget | 1.29.380 | |

`python3` on PATH is the empty Microsoft Store alias. Use `python`, `py` or `uv run`.

## Dependencies checked on PyPI (2026-10-17)

All have Windows wheels for Python 3.12 and 3.14.

| Package | Version | License | Use |
|---|---|---|---|
| PySide6-Essentials | 6.12.0 | LGPL-3.0 (or GPL) | Desktop UI (installed, M1) |
| pytest | 9.1.1 | MIT | Tests (installed, M1) |
| pytest-qt | 4.5.0 | MIT | Qt tests (installed, M1) |
| ruff | 0.17.1 | MIT | Lint/format (installed, M1) |
| httpx | 0.28.1 | BSD-3-Clause | HTTP candidate, evaluated in M2 |
| aiohttp | 3.14.5 | Apache-2.0 AND MIT | HTTP candidate, evaluated in M2 |
| pytest-asyncio | 1.4.0 | Apache-2.0 | Only if async code is chosen |
| mypy | 2.4.0 | MIT | Optional type checking |
| PyInstaller | 6.22.3 | GPL-2.0+ with bootloader exception | Packaging, M10 |

## Findings that affect the design

1. **Controlled Folder Access is enabled** (Windows Defender). Documents, Desktop, Pictures,
   Videos and Music refuse writes from unrecognized programs. Creating the project in Documents
   failed for this reason. SDM must detect and explain blocked writes when the user picks one of
   those folders as a download destination.
2. **Long paths are disabled** (`LongPathsEnabled = 0`), so full paths are limited to about 260
   characters. Filename sanitization must enforce this.
3. **PowerShell script execution is restricted for the user** (no policy set, so the Windows
   default applies), so `.venv\Scripts\Activate.ps1` fails. Use `uv run` instead.
4. **IDM 6.42 build 22 is installed** (`IDMan.exe` file version), so it's available as a
   black-box reference for Stage A observations.
5. **Chrome native messaging hosts already registered:** `com.tonec.idm` (IDM),
   `org.freedownloadmanager.fdm5.cnh` (Free Download Manager), plus Microsoft hosts. Other
   download-manager extensions may intercept downloads during SDM testing, so test in a separate
   Chrome profile. SDM's host name must not collide with these.
