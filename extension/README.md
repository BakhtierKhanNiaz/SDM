# SDM's Chrome extension

Adds **Download with SDM** to the right-click menu of links. Clicking it hands the link to SDM,
which opens its Add URL dialog with the address filled in. Nothing downloads until you press
**Download** there.

The extension asks for two permissions only: `contextMenus` (the menu item) and
`nativeMessaging` (to start SDM's helper program). It can't read pages, see your browsing or
watch your downloads. How it works and why: ADR-0014 in
[docs/decisions](../docs/decisions/architecture-decision-records.md).

## Set up (once, in a separate Chrome profile)

IDM and Free Download Manager also hook into Chrome, so try SDM in a profile of its own.

1. In Chrome, click your profile picture (top right), then **Add**, then **Continue without
   an account**. Name the profile `SDM test`.
2. In that profile, open `chrome://extensions`, turn on **Developer mode** (top right), click
   **Load unpacked** and choose the folder `D:\Projects\SDM\extension\chrome`.
3. Copy the **ID** shown on SDM's card: 32 letters from a to p.
4. Register SDM's helper for that ID (it writes one per-user registry value and two files in
   `%LOCALAPPDATA%\SDM\bridge`):

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

## If something goes wrong

The toolbar icon shows a red **!** and its tooltip says why:

| Tooltip | Meaning |
|---|---|
| SDM's browser bridge isn't installed for this extension | Chrome was already running when step 4 ran: quit it completely (every window, and the tray icon) and open it again. Otherwise step 4 hasn't run, or ran in another Windows account |
| ...installed for a different extension ID | The extension's ID changed: run step 4 with the new one |
| SDM didn't start | SDM couldn't start within 15 seconds: start it by hand and try again |
| Too many links are waiting in SDM | Five Add URL dialogs are already waiting: close some |

For more detail, open `chrome://extensions`, click **service worker** on SDM's card and look
at the Console. The link itself is never logged.

## Tests

```powershell
cd extension
node --test
```

Node's built-in test runner checks the menu, the message and the replies against a fake
`chrome` object. There's nothing to install.
