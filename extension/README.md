# SDM's Chrome extension

Adds **Download with SDM** to the right-click menu of links and of video and audio players.
Clicking it hands the address (and the page it was on) to SDM, which opens its Add URL dialog
filled in. Nothing downloads until you press **Download** there.

Optionally, it can also **send your downloads to SDM automatically** (off until you turn it on;
see below).

It always has two permissions: `contextMenus` (the menu item) and `nativeMessaging` (to start
SDM's helper program). It can't read pages or cookies. Only if you turn on automatic capture
does it get `downloads` (and `storage`, to remember the minimum size), and Chrome asks you
first. How it works and why: ADR-0014 and ADR-0015 in
[docs/decisions](../docs/decisions/architecture-decision-records.md).

## Set up (once, in a separate Chrome profile)

IDM and Free Download Manager also hook into Chrome, so try SDM in a profile of its own.

1. In Chrome, click your profile picture (top right), then **Add**, then **Continue without
   an account**. Name the profile `SDM test`.
2. In that profile, open `chrome://extensions`, turn on **Developer mode** (top right), click
   **Load unpacked** and choose the folder `D:\Projects\SDM\extension\chrome`.
3. Copy the **ID** shown on SDM's card: 32 letters from a to p.
4. In **your own** PowerShell window (Start, type PowerShell), in `D:\Projects\SDM`,
   register SDM's helper for that ID. It writes one per-user registry value and two files in
   `%LOCALAPPDATA%\SDM\bridge`. Don't let an AI assistant's sandboxed shell run this: its
   registry changes aren't visible to your Chrome.

   ```powershell
   uv run python -m sdm.bridge.install --extension-id <the ID>
   ```

5. **Quit Chrome completely** (every window, and its tray icon if it has one) and open it
   again. A Chrome that was already running when you registered keeps answering "host not
   found".

The ID comes from the folder's location, so moving the folder changes it: run step 4 again.

To check the setup without clicking anything: `node scripts/chrome_bridge_check/check.mjs`
(from the project folder). It starts a throwaway headless Chrome with a temporary profile,
loads this extension and asks SDM's host to refuse a test link; `OK` means Chrome finds the
host and the host runs.
To remove the registration: `uv run python -m sdm.bridge.install --uninstall`.

## Automatic capture (optional)

1. Click SDM's icon in Chrome's toolbar (pin it from the puzzle-piece menu if you don't see it).
2. Tick **Send my downloads to SDM**. Chrome asks whether SDM may "Manage your downloads":
   choose **Allow**.
3. Optionally set **Leave files smaller than ___ MB to Chrome** (it applies when Chrome already
   knows the size).

From then on, when Chrome starts a download, the extension stops Chrome's copy, removes it
from Chrome's download list and sends it to SDM, which asks you to confirm. Incognito windows,
`blob:` downloads and files below the minimum stay in Chrome. If SDM can't take a download
(it couldn't start, or too many dialogs are waiting), Chrome downloads it as usual and the
icon's tooltip says why. Untick the box to stop; Chrome takes the permission back.

What SDM receives: the address, the page it came from (sent to the server like a browser
would), Chrome's file name, size and type. Never cookies: a download that needs you to be
logged in may fail in SDM; untick the box and download it in Chrome.

After updating SDM's files, open `chrome://extensions` and click the **reload** arrow on SDM's
card so Chrome uses the new version.

## If something goes wrong

The toolbar icon shows a red **!** and its tooltip says why:

| Tooltip | Meaning |
|---|---|
| SDM's browser bridge isn't installed for this extension | Check in your own PowerShell: `reg query "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.sdm.bridge"`. If it's missing, step 4 didn't run for your account (or ran in a sandbox): run it yourself, then restart Chrome |
| ...installed for a different extension ID | The extension's ID changed: run step 4 with the new one |
| SDM didn't start | SDM couldn't start within 15 seconds: start it by hand and try again |
| Too many links are waiting in SDM | Five Add URL dialogs are already waiting: close some |
| ...Chrome downloaded it instead | Capture couldn't hand the download to SDM, so Chrome kept it (the first part says why) |

For more detail, open `chrome://extensions`, click **service worker** on SDM's card and look
at the Console. The link itself is never logged.

## Tests

```powershell
cd extension
node --test
```

Node's built-in test runner checks the menu, the message and the replies against a fake
`chrome` object. There's nothing to install.
