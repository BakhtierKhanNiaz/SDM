# SDM's browser extension

Sends your downloads to SDM: click a download and SDM's dialog opens instead of the browser's
Save As. It also adds **Download with SDM** to the right-click menu of links and of video and
audio players. It works in **Google Chrome, Microsoft Edge, Brave** and other Chromium
browsers, and in **Mozilla Firefox**.

Its permissions, all asked for at install: `downloads` ("Manage your downloads", to send
downloads to SDM), `storage` (its two settings), `contextMenus` (the menu item) and
`nativeMessaging` (to reach SDM on this computer). It never reads pages or cookies and has no
access to any website. How it works and why: ADR-0014, ADR-0015 and ADR-0019 in
[docs/decisions](../docs/decisions/architecture-decision-records.md).

## Set up

1. **Connect SDM to your browsers.** SDM's welcome assistant does this on first start (later:
   **Help > Setup assistant**). It finds your browsers and registers SDM for the ones you tick.
   Nothing to type: the extension's IDs are fixed.
2. **Install the extension** in each browser:
   - **Chrome, Brave, other Chromium browsers:** download `sdm-chromium-<version>.zip` from the
     [latest release](../../../releases/latest) and unzip it to a folder you'll keep. Open
     `chrome://extensions` (Brave: `brave://extensions`), turn on **Developer mode**, click
     **Load unpacked** and choose that folder.
   - **Microsoft Edge:** from Microsoft Edge Add-ons once SDM is listed there, or like Chrome at
     `edge://extensions` (**Developer mode**, **Load unpacked**).
   - **Firefox:** from Firefox Add-ons once SDM is listed there (Firefox only installs add-ons
     signed by Mozilla).
3. **Restart the browser** completely if it was already open.

Start SDM normally (from the Start menu). If SDM runs **as administrator**, Windows doesn't let
the browser reach it, and SDM warns you.

## Sending downloads to SDM

This is on as soon as the extension is installed: it stops the browser's own copy of each new
download and SDM asks you to confirm it. To turn it off (or on again), click SDM's toolbar
icon (pin it from the puzzle-piece menu if you don't see it) and untick (or tick) **Send my
downloads to SDM**; right-click still works while it's off.

Private (incognito) windows, `blob:` downloads and files below the minimum size (set in the
same panel) stay in the browser. If SDM can't take a download, the browser downloads it as
usual, once.

- **Chromium browsers** capture before their "Save As" window appears.
- **Firefox** has no hook before its "Save As" window, so with "Always ask where to save files"
  on, Firefox's window may appear first; right-click works the same as everywhere.

The extension sends SDM the address, the page it came from, the browser's file name, size and
type. Never cookies: a download that needs you to be logged in may fail in SDM; untick the box
and download it in the browser.

## If something goes wrong

The toolbar icon shows a red **!**; click the icon to read the last problem.

| Message | Meaning |
|---|---|
| SDM's browser bridge isn't installed for this extension | Run **Help > Setup assistant** in SDM, tick this browser, then restart the browser |
| ...installed for a different extension ID | An extension loaded from an old copy: remove it and load the current zip |
| SDM didn't start | SDM couldn't start within 15 seconds: start it from the Start menu and try again |
| SDM couldn't take the link | Is SDM running as administrator? Start it normally. Details: `%LOCALAPPDATA%\SDM\logs\bridge-host.log` |
| Too many links are waiting in SDM | Five Add URL dialogs are already waiting: close some |

## For developers

- `extension/chrome/` is the source (Manifest V3). The `key` in `manifest.json` is a public key
  that fixes the Chromium ID to `klbnhggmneoiamogpgbkajkdklfacohb`; no private key exists or is
  needed, since the extension is never packed as a signed `.crx`.
- `uv run python scripts/build_extensions.py` builds `dist\extension\`: the Chromium zip, an
  Edge Add-ons zip (without `key`; the store assigns its own ID, which then goes into
  `EDGE_STORE_EXTENSION_ID` in `src/sdm/bridge/browsers.py`), and the Firefox zip (its own
  manifest with the add-on ID `sdm@sdm-download-manager`, and the background modules joined
  into one classic script, since Firefox runs background scripts, not service workers).
- Tests: `cd extension; node --test` (nothing to install), and
  `node scripts/chrome_bridge_check/check.mjs`, which loads the extension in a throwaway
  headless Chrome (set `CHROME` to `msedge.exe` for Edge) and checks it reaches SDM's helper.
