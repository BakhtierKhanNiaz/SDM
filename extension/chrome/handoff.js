// The extension's logic, kept free of chrome.* calls so `node --test` can check it.
// SDM checks every message again on its side; these checks only avoid pointless handoffs.

export const HOST_NAME = "com.sdm.bridge";
export const MENU_ID = "sdm-download-link";
export const VIDEO_MENU_ID = "sdm-download-video";
export const VIDEO_REQUEST = "sdm-video"; // the toolbar panel asks the worker to send a page

// M13: the button over videos runs on web pages only after the user allowed page access.
export const PAGE_ACCESS = { origins: ["http://*/*", "https://*/*"] };
export const VIDEO_BUTTON_SCRIPT = {
  id: "sdm-video-button",
  matches: ["http://*/*", "https://*/*"],
  js: ["video-button.js"],
  runAt: "document_idle",
  allFrames: true, // embedded players (an embed page inside an article) get it too
};
export const MAX_URL_LENGTH = 8192;
const MAX_NAME_LENGTH = 255;
const MAX_SIZE = 2 ** 53;

export function menuItem() {
  return {
    id: MENU_ID,
    title: "Download with SDM",
    contexts: ["link", "video", "audio"],
    // Applies to the link's or the player's address: blob: and data: players never match.
    targetUrlPatterns: ["http://*/*", "https://*/*"],
  };
}

// M12: the whole page as a video (SDM's video add-on, yt-dlp), from anywhere on an http(s)
// page or on a player. Streaming sites' players play blob: addresses SDM can't download, so
// the page's own address is what SDM needs.
export function videoMenuItem() {
  return {
    id: VIDEO_MENU_ID,
    title: "Download this video with SDM",
    contexts: ["page", "video"],
    documentUrlPatterns: ["http://*/*", "https://*/*"],
  };
}

// A plain http(s) address without a user name or password, or null.
export function webUrl(value) {
  if (typeof value !== "string" || value.length === 0 || value.length > MAX_URL_LENGTH) {
    return null;
  }
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    return null;
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
  if (parsed.username !== "" || parsed.password !== "") return null;
  return value;
}

// The last part of a path Chrome gives (e.g. "C:\Users\me\Downloads\a.zip" -> "a.zip"), if it
// is a name SDM will accept: no separators, colons or control characters, not just dots.
export function bareName(path) {
  if (typeof path !== "string") return null;
  const name = path.split(/[\\/]/).pop();
  if (!name || name.length > MAX_NAME_LENGTH) return null;
  if (/[:\u0000-\u001f\u007f]/.test(name) || name.replace(/[ .]/g, "") === "") return null;
  return name;
}

// The message SDM accepts (version 2), or null when the address isn't one SDM downloads.
// The hints are optional: anything that doesn't pass its check is simply left out.
export function messageFor(url, { referrer, filename, size, mime, source = "menu" } = {}) {
  if (webUrl(url) === null) return null;
  const message = { version: 2, type: "download", url };
  if (webUrl(referrer) !== null) message.referrer = referrer;
  const name = bareName(filename);
  if (name !== null) message.filename = name;
  if (Number.isInteger(size) && size > 0 && size <= MAX_SIZE) message.size = size;
  if (typeof mime === "string" && /^[\x21-\x7e]{1,200}$/.test(mime)) message.mime = mime;
  message.source = source === "capture" || source === "video" ? source : "menu";
  return message;
}

// A page to download as a video (M12): only its address, marked "video".
export function videoMessage(pageUrl) {
  return messageFor(pageUrl, { source: "video" });
}

// From a right-click: for "Download this video", the page; else a player's own address when
// the click was on video or audio, or the link's. The page (or frame) becomes the referrer.
export function menuMessage(info) {
  if (info.menuItemId === VIDEO_MENU_ID) return videoMessage(info.pageUrl);
  const onMedia = info.mediaType === "video" || info.mediaType === "audio";
  const url = onMedia && info.srcUrl ? info.srcUrl : info.linkUrl;
  return messageFor(url, { referrer: info.frameUrl || info.pageUrl, source: "menu" });
}

const ERROR_TEXT = {
  bad_origin: "SDM refused this extension.",
  bad_request: "SDM can't download this link.",
  busy: "Too many links are waiting in SDM; finish those first.",
  not_running: "SDM didn't start. Open SDM and try again.",
  failed: "SDM couldn't take the link.",
};

export const NOT_A_LINK_TEXT = "SDM only downloads http:// and https:// links.";
export const NOT_A_PAGE_TEXT = "Open the video's page (an http:// or https:// page) first.";

// What to show after SDM replied: {ok, text}.
export function describeReply(reply) {
  if (reply !== null && typeof reply === "object" && reply.ok === true) {
    return { ok: true, text: "Sent to SDM." };
  }
  const code = reply !== null && typeof reply === "object" ? reply.error : undefined;
  return { ok: false, text: ERROR_TEXT[code] ?? ERROR_TEXT.failed };
}

// What to show when Chrome couldn't run SDM's host at all.
export function describeFailure(error) {
  const message = String(error?.message ?? error);
  if (message.includes("host not found")) {
    return {
      ok: false,
      text: "SDM's browser bridge isn't installed for this extension. If you just installed it, quit Chrome completely and open it again.",
    };
  }
  if (message.includes("Access to the specified native messaging host is forbidden")) {
    return { ok: false, text: "SDM's browser bridge is installed for a different extension ID." };
  }
  return { ok: false, text: "Couldn't reach SDM." };
}
