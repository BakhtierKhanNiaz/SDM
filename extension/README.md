# SDM's browser extension

Sends your downloads to SDM: click a download and SDM's dialog opens instead of the browser's
Save As. It also adds **Download with SDM** to the right-click menu of links and of video and
audio players. It works in **Google Chrome, Microsoft Edge, Brave** and other Chromium
browsers, and in **Mozilla Firefox**.

Its permissions, all asked for at install: `downloads` ("Manage your downloads", to send
downloads to SDM), `storage` (its two settings), `contextMenus` (the menu items),
`nativeMessaging` (to reach SDM on this computer), `activeTab` (the current tab's address,
and only after you click SDM's toolbar icon; browsers show no warning for it) and `scripting`
(for the video button). It has no access to any website, never reads pages, and never reads
cookies. The one exception is optional: if you turn on the video button, the browser asks
for page access, and the button then looks only at where videos are on the page. How it
works and why: ADR-0014, ADR-0015, ADR-0019 and ADR-0021 in
[docs/decisions](../docs/decisions/architecture-decision-records.md).

## Set up

The extension comes with SDM (in `SDM\extension` next to SDM.exe).

1. **SDM's welcome assistant** (on first start; later **Help > Add the browser extension**)
   registers SDM for the browsers you tick.
2. **Press "Add to Chrome"** (or Edge, Brave) there. The browser opens a new tab and SDM
   copies the extension's folder for you. Nothing is added yet: then, in the browser,
   1. type `chrome://extensions` (Edge: `edge://extensions`, Brave: `brave://extensions`) in
      the address bar and press Enter (browsers don't let other programs open this page),
   2. turn on **Developer mode** (top right),
   3. click **Load unpacked**,
   4. press **Ctrl+V** in the folder box and choose **Select Folder**.
3. **Firefox:** from Firefox Add-ons once SDM is listed there (Firefox only installs add-ons
   signed by Mozilla; Firefox 128 or newer).
4. **Restart the browser** completely if it was already open.

Browsers don't let programs add extensions by themselves, which is why these steps are
needed once. When you update SDM, the extension updates too after the browser restarts.

## The SDM button on videos

Click SDM's toolbar icon and tick **Show the SDM button on videos**. The browser asks whether
SDM may "read and change data on all websites": it needs that to see where videos are. From
then on, a small **SDM Download** button appears at the top-right of a video when it plays or
when the mouse is over it. Click it and SDM asks the quality. The **x** hides it on that
page. Untick the switch to turn the button off; the browser then takes the access back.

Start SDM normally (from the Start menu). If SDM runs **as administrator**, Windows doesn't let
the browser reach it, and SDM warns you.

## Downloading a video from a page

On a video's page, right-click anywhere on the page (or on the video) and choose **Download
this video with SDM**, or click SDM's toolbar icon and then **Download this video with SDM**.
SDM opens Add URL set to a video, at the quality you chose last time (720p, 1080p, 4K or
audio). This uses SDM's video add-on (yt-dlp): if it's off, SDM asks once to turn it on. The
extension only sends the page's address; it never reads the page.

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
| SDM isn't connected to this browser | Usually SDM was uninstalled or reinstalled, which removes the connection. Open SDM: since 1.2.1 it reconnects the browsers you chose when it starts. If not, run **Help > Setup assistant**, tick this browser and finish; if it still fails, quit the browser completely and open it again |
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
