// SDM's service worker: the right-click item on links and players, and (only if the user turned
// it on in the toolbar panel, which grants the "downloads" permission) automatic capture.
// It never reads pages and has no access to any website's content or cookies.

import { captureMessage, DEFAULT_SETTINGS, reasonToSkip, SETTINGS_KEY } from "./capture.js";
import {
  HOST_NAME,
  MENU_ID,
  NOT_A_LINK_TEXT,
  describeFailure,
  describeReply,
  menuItem,
  menuMessage,
} from "./handoff.js";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => chrome.contextMenus.create(menuItem()));
});

chrome.contextMenus.onClicked.addListener((info) => {
  if (info.menuItemId !== MENU_ID) return;
  const message = menuMessage(info);
  if (message === null) {
    showStatus({ ok: false, text: NOT_A_LINK_TEXT });
    return;
  }
  // Clear the last click's status first, so an old "!" is never mistaken for this one.
  showStatus({ ok: true, text: "" });
  return send(message).then(showStatus);
});

// ----- automatic capture -----

let watching = false;
function watchDownloads() {
  // chrome.downloads exists only while the permission is granted. Registering at the top level
  // lets Chrome wake this worker for new downloads; onAdded covers turning capture on later.
  if (chrome.downloads && !watching) {
    chrome.downloads.onCreated.addListener(onDownloadCreated);
    watching = true;
  }
}
watchDownloads();
chrome.permissions.onAdded.addListener(watchDownloads);

export async function onDownloadCreated(item) {
  if (!(await chrome.permissions.contains({ permissions: ["downloads"] }))) return;
  const settings = await loadSettings();
  if (reasonToSkip(item, { ...settings, ownId: chrome.runtime.id }) !== null) return;
  const message = captureMessage(item);
  if (message === null) return;

  // Stop Chrome's copy before SDM starts, so the file is never downloaded twice. A small file
  // may already be finished: then Chrome keeps it and SDM isn't asked.
  await chrome.downloads.cancel(item.id);
  const [after] = await chrome.downloads.search({ id: item.id });
  if (after && after.state === "complete") return;
  await chrome.downloads.erase({ id: item.id });

  showStatus({ ok: true, text: "" });
  const status = await send(message);
  if (status.ok) {
    showStatus(status);
    return;
  }
  // SDM can't take it (not running and couldn't start, busy, refused): give it back to
  // Chrome. A download this extension starts is marked with its ID, so it isn't captured again.
  try {
    await chrome.downloads.download({ url: item.url });
    showStatus({ ok: false, text: `${status.text} Chrome downloaded it instead.` });
  } catch (error) {
    console.warn(`SDM: Chrome couldn't restart the download: ${String(error?.message ?? error)}`);
    showStatus({ ok: false, text: `${status.text} Chrome couldn't download it either.` });
  }
}

async function loadSettings() {
  if (!chrome.storage?.local) return { ...DEFAULT_SETTINGS };
  const stored = await chrome.storage.local.get(SETTINGS_KEY);
  return { ...DEFAULT_SETTINGS, ...(stored?.[SETTINGS_KEY] ?? {}) };
}

// ----- talking to SDM -----

// Chrome starts SDM's host for this one message and passes back its one reply.
async function send(message) {
  try {
    return describeReply(await chrome.runtime.sendNativeMessage(HOST_NAME, message));
  } catch (error) {
    // Chrome's own wording (it never contains the link) helps when diagnosing setup.
    console.warn(`SDM: Chrome said: ${String(error?.message ?? error)}`);
    return describeFailure(error);
  }
}

// A "!" on the toolbar icon when something went wrong; its tooltip says what.
function showStatus(status) {
  chrome.action.setBadgeText({ text: status.ok ? "" : "!" });
  chrome.action.setTitle({ title: status.ok ? "SDM" : `SDM: ${status.text}` });
  if (!status.ok) console.warn(`SDM: ${status.text}`); // the link itself is never logged
}
