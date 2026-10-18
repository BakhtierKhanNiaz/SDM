// SDM's service worker: one right-click menu item on links, and nothing else.
// It never reads pages, never watches downloads and has no access to any website.

import {
  HOST_NAME,
  MENU_ID,
  NOT_A_LINK_TEXT,
  describeFailure,
  describeReply,
  menuItem,
  messageFor,
} from "./handoff.js";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => chrome.contextMenus.create(menuItem()));
});

chrome.contextMenus.onClicked.addListener((info) => {
  if (info.menuItemId !== MENU_ID) return;
  const message = messageFor(info.linkUrl);
  if (message === null) {
    showStatus({ ok: false, text: NOT_A_LINK_TEXT });
    return;
  }
  // Clear the last click's status first, so an old "!" is never mistaken for this one.
  showStatus({ ok: true, text: "" });
  // Chrome starts SDM's host for this one message and passes back its one reply.
  return chrome.runtime
    .sendNativeMessage(HOST_NAME, message)
    .then((reply) => showStatus(describeReply(reply)))
    .catch((error) => {
      // Chrome's own wording (it never contains the link) helps when diagnosing setup.
      console.warn(`SDM: Chrome said: ${String(error?.message ?? error)}`);
      showStatus(describeFailure(error));
    });
});

// A "!" on the toolbar icon when something went wrong; its tooltip says what.
function showStatus(status) {
  chrome.action.setBadgeText({ text: status.ok ? "" : "!" });
  chrome.action.setTitle({ title: status.ok ? "SDM" : `SDM: ${status.text}` });
  if (!status.ok) console.warn(`SDM: ${status.text}`); // the link itself is never logged
}
